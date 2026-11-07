"""Capture README screenshots for the SureDesk chat and review workbench."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = ROOT / "docs" / "screenshots"
CHROMIUM = Path.home() / (
    "Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/"
    "Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
)

PROBLEMS = [
    {
        "id": "pp_7f3a91c2d4e5",
        "session_id": "sess_8ab21c",
        "trigger_type": "CONFIDENCE_GATE",
        "query": "定制款键盘拆封后还能七天无理由退货吗？",
        "rewritten_query": "客制化机械键盘拆封后是否适用七天无理由退货？",
        "frequency": 4,
        "sessions": ["sess_8ab21c", "sess_2f91da", "sess_71ce02"],
        "answer": "当前知识库未找到该商品类目的退货例外说明，已停止生成承诺性回答。",
        "operator_status": "PENDING",
        "standard_answer": "",
        "created_at": "2026-11-07T10:24:00+01:00",
    },
    {
        "id": "pp_2b8d64a0c913",
        "session_id": "sess_31bd77",
        "trigger_type": "USER_THUMBS_DOWN",
        "query": "退货运费谁承担？",
        "rewritten_query": "七天无理由退货产生的退货运费由买家还是商家承担？",
        "frequency": 3,
        "sessions": ["sess_31bd77", "sess_9ac410"],
        "answer": "退货产生的运费需要根据商品是否包邮、退货原因和平台规则综合判断。",
        "operator_status": "PENDING",
        "standard_answer": "",
        "created_at": "2026-11-07T09:52:00+01:00",
    },
    {
        "id": "pp_91c47e02ab55",
        "session_id": "sess_550ae1",
        "trigger_type": "CONFIDENCE_GATE",
        "query": "发票可以开公司抬头吗？",
        "rewritten_query": "订单是否支持开具公司抬头的增值税普通发票？",
        "frequency": 2,
        "sessions": ["sess_550ae1", "sess_0c7d93"],
        "answer": "",
        "operator_status": "PENDING",
        "standard_answer": "",
        "created_at": "2026-11-07T09:18:00+01:00",
    },
    {
        "id": "pp_5e0a38c7d124",
        "session_id": "sess_71ce02",
        "trigger_type": "USER_THUMBS_DOWN",
        "query": "预售商品什么时候发货？",
        "rewritten_query": "预售商品的承诺发货时间与延迟赔付规则是什么？",
        "frequency": 6,
        "sessions": ["sess_71ce02", "sess_8ab21c", "sess_31bd77", "sess_9ac410"],
        "answer": "预售商品通常在页面标注的时间内发货，具体以订单详情为准。",
        "operator_status": "PENDING",
        "standard_answer": "",
        "created_at": "2026-11-06T18:40:00+01:00",
    },
]

CHAT_ANSWER = (
    "订单 order_1002 已经发货了。顺丰速运的运单号是 SF100288889999，"
    "最新轨迹显示快件正在发往北京顺义集散中心。\n\n"
    "预计明天下午前完成派送。如果超过 24 小时没有更新，可以回复「转人工」，"
    "我们会帮你联系承运方。"
)

FOLLOW_UP_ANSWER = (
    "预计明天 14:00 前送到北京朝阳区。派件前快递员会电话联系；"
    "如果家里没人，也可以在应用里改约到周末。"
)


def sse(event: str, payload: dict | str) -> str:
    """Build one Server-Sent Events frame."""
    data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def chat_stream_body(
    answer: str = CHAT_ANSWER,
    thought: str = "识别为物流查询，正在核验订单归属并读取承运方最新轨迹。",
    evidence: list[dict] | None = None,
) -> str:
    """Build a deterministic streamed answer for screenshots."""
    frames = [sse("thought", {"thought": thought})]
    chunk_size = 14
    for index in range(0, len(answer), chunk_size):
        frames.append(sse("answer", {"chunk": answer[index : index + chunk_size]}))
    frames.append(
        sse(
            "evidence",
            evidence
            or [
                {"doc_title": "订单 order_1002 · 履约状态"},
                {"doc_title": "电商售后 FAQ · 物流时效"},
            ],
        )
    )
    return "".join(frames)


def get_token(role: str, explicit: str | None) -> str:
    """Use an explicit token or mint one from AUTH_SECRET for local screenshots."""
    if explicit:
        return explicit
    from newcode.api.auth import create_access_token

    user_id = "user_buyer_1" if role == "BUYER" else "user_operator_1"
    return create_access_token(user_id, role)


def install_token(context, token: str) -> None:
    """Seed localStorage before any page script runs."""
    context.add_init_script(
        "localStorage.setItem('suredesk_access_token', " + json.dumps(token) + ");"
    )


def wait_for_page(page: Page) -> None:
    """Wait for layout, fonts, and the entry animation to settle."""
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(650)


def capture_chat(page: Page, output: Path, mobile: bool = False) -> None:
    """Capture the welcome state and a completed conversation."""
    def fulfill_chat(route):
        post_data = route.request.post_data or ""
        if "明天" in post_data:
            body = chat_stream_body(
                FOLLOW_UP_ANSWER,
                "沿用上一轮的订单上下文，读取同城派送时段。",
                [
                    {"doc_title": "顺丰速运 · 派送时效说明"},
                    {"doc_title": "订单 order_1002 · 收货地址"},
                ],
            )
        else:
            body = chat_stream_body()
        route.fulfill(status=200, content_type="text/event-stream", body=body)

    page.route(
        "**/api/chat/stream",
        fulfill_chat,
    )
    page.goto("http://127.0.0.1:8000/chat")
    wait_for_page(page)
    if not mobile:
        page.screenshot(path=str(output / "chat-welcome.png"), full_page=False)

    page.locator(".prompt").first.click()
    page.wait_for_selector(".feedback-bar", timeout=8000)
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(500)
    if not mobile:
        page.screenshot(path=str(output / "chat-conversation.png"), full_page=False)

    page.fill("#userInput", "那明天大概几点能送到？")
    page.press("#userInput", "Enter")
    page.wait_for_function(
        "document.querySelectorAll('.feedback-bar').length >= 2",
        timeout=8000,
    )
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(500)

    if not mobile:
        page.screenshot(path=str(output / "chat-multiturn.png"), full_page=False)

    page.screenshot(
        path=str(output / ("chat-mobile.png" if mobile else "chat-multiturn.png")),
        full_page=False,
    )


def capture_workbench(page: Page, output: Path) -> None:
    """Capture the review queue with a selected problem."""

    def fulfill(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"success": True, "total": len(PROBLEMS), "problems": PROBLEMS},
                ensure_ascii=False,
            ),
        )

    page.route("**/api/workbench/problems**", fulfill)
    page.goto("http://127.0.0.1:8000/workbench")
    wait_for_page(page)
    page.wait_for_selector(".problem-row")
    page.locator(".problem-row").nth(1).click()
    page.wait_for_timeout(450)
    page.screenshot(path=str(output / "workbench.png"), full_page=True)


def main() -> int:
    """Render all README screenshots into the output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--buyer-token", default=os.environ.get("SUREDESK_BUYER_TOKEN"))
    parser.add_argument("--operator-token", default=os.environ.get("SUREDESK_OPERATOR_TOKEN"))
    args = parser.parse_args()

    if not CHROMIUM.exists():
        print(f"Chromium not found at {CHROMIUM}", file=sys.stderr)
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    buyer_token = get_token("BUYER", args.buyer_token)
    operator_token = get_token("OPERATOR", args.operator_token)
    errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(CHROMIUM), headless=True)

        desktop = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            locale="zh-CN",
        )
        install_token(desktop, buyer_token)
        page = desktop.new_page()
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        capture_chat(page, args.output)
        desktop.close()

        workbench = browser.new_context(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=2,
            locale="zh-CN",
        )
        install_token(workbench, operator_token)
        workbench_page = workbench.new_page()
        workbench_page.on(
            "console",
            lambda message: errors.append(message.text) if message.type == "error" else None,
        )
        capture_workbench(workbench_page, args.output)
        workbench.close()

        mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            locale="zh-CN",
            is_mobile=True,
        )
        install_token(mobile, buyer_token)
        mobile_page = mobile.new_page()
        capture_chat(mobile_page, args.output, mobile=True)
        mobile.close()

        browser.close()

    if errors:
        print("Console errors:", file=sys.stderr)
        for message in errors:
            print("  " + message, file=sys.stderr)

    print(f"Screenshots written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

