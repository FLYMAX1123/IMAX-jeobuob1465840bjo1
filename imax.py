
import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

THEATER_NAME = "CGV 광교"
THEATER_CODE = "0257"

WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_imax.json"

BOOKING_PAGE = "https://cgv.co.kr/cnm/movieBook/cinema"
API_URL = "https://cgv.co.kr/api/v1/booking/searchMovScnInfo"

KST = ZoneInfo("Asia/Seoul")


def get_imax_schedules():

    print("=" * 40)
    print("CGV 광교 IMAX 확인 시작")
    print("접속 방식: Playwright Chromium")
    print("=" * 40)

    imax_list = []

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        try:
            context = browser.new_context(
                locale="ko-KR",
                timezone_id="Asia/Seoul"
            )

            page = context.new_page()

            # 브라우저로 예매 페이지에 먼저 접속해 세션 확보
            response = page.goto(
                BOOKING_PAGE,
                wait_until="domcontentloaded",
                timeout=60000
            )

            if response is None or response.status >= 400:
                status = response.status if response else "응답 없음"
                raise Exception(
                    f"CGV 예매 페이지 접속 실패: {status}"
                )

            print("예매 페이지 접속 성공:", response.status)

            today = datetime.now(KST).date()

            for i in range(14):

                target_date = today + timedelta(days=i)
                date_text = target_date.strftime("%Y%m%d")

                params = {
                    "coCd": "A420",
                    "siteNo": THEATER_CODE,
                    "scnYmd": date_text,
                    "rtctlScopCd": "08"
                }

                try:
                    api_response = context.request.get(
                        API_URL,
                        params=params,
                        headers={
                            "Accept": "application/json, text/plain, */*",
                            "Accept-Language": "ko-KR,ko;q=0.9",
                            "Referer": BOOKING_PAGE
                        },
                        timeout=30000
                    )

                    print(
                        f"{date_text} API 상태:",
                        api_response.status
                    )

                    if api_response.status != 200:
                        raise Exception(
                            f"CGV API 오류: {api_response.status}"
                        )

                    data = api_response.json()

                    if data.get("statusCode") != 0:
                        raise Exception(
                            f"CGV 응답 오류: {data}"
                        )

                    schedules = data.get("data") or []

                    for schedule in schedules:

                        screen_name = schedule.get("scnsNm") or ""
                        display_screen_name = (
                            schedule.get("expoScnsNm") or ""
                        )
                        movie_format = (
                            schedule.get("movkndDsplNm") or ""
                        )

                        search_text = " ".join([
                            screen_name,
                            display_screen_name,
                            movie_format
                        ]).upper()

                        if "IMAX" not in search_text:
                            continue

                        movie_name = (
                            schedule.get("movNm")
                            or schedule.get("prodNm")
                            or "영화명 없음"
                        )

                        start_time = schedule.get("scnsrtTm") or ""

                        schedule_id = (
                            f"{date_text}|{movie_name}|"
                            f"{screen_name}|{start_time}"
                        )

                        item = {
                            "id": schedule_id,
                            "date": date_text,
                            "movie": movie_name,
                            "screen": display_screen_name or screen_name,
                            "time": start_time
                        }

                        imax_list.append(item)

                        print("IMAX 발견:", item)

                except Exception as error:
                    # 일부 날짜라도 조회 실패하면 상태 파일을
                    # 갱신하지 않도록 전체 실행을 중단
                    raise Exception(
                        f"{date_text} 조회 실패: {error}"
                    )

            context.close()

        finally:
            browser.close()

    unique_imax = {
        item["id"]: item
        for item in imax_list
    }

    return list(unique_imax.values())


def load_previous_imax():

    if not os.path.exists(STATE_FILE):
        return None

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception as error:
        raise Exception(
            f"기존 IMAX 기록을 읽지 못했습니다: {error}"
        )


def save_imax(imax_list):

    with open(STATE_FILE, "w", encoding="utf-8") as file:
        json.dump(
            imax_list,
            file,
            ensure_ascii=False,
            indent=2
        )


def send_discord(new_imax):

    if not WEBHOOK_URL:
        raise Exception("DISCORD_WEBHOOK_URL이 없습니다.")

    message = (
        f"🎥 **{THEATER_NAME} IMAX 예매 오픈!**\n\n"
        "새로운 IMAX 상영이 발견되었습니다.\n\n"
    )

    shown = set()

    for item in new_imax:

        key = (
            item["date"],
            item["movie"],
            item["screen"]
        )

        if key in shown:
            continue

        shown.add(key)

        date = datetime.strptime(
            item["date"],
            "%Y%m%d"
        ).strftime("%Y년 %m월 %d일")

        time_text = item.get("time", "")

        if len(time_text) == 4:
            time_text = (
                f"{time_text[:2]}:{time_text[2:]}"
            )

        message += (
            f"🎬 **{item['movie']}**\n"
            f"📅 {date}\n"
            f"🎥 {item['screen']}\n"
            f"🕒 {time_text}\n\n"
        )

    message += (
        "🔔 CGV 광교에서 새로운 IMAX 상영이 열렸습니다!"
    )

    with sync_playwright() as p:

        request = p.request.new_context()

        try:
            response = request.post(
                WEBHOOK_URL,
                data=json.dumps(
                    {"content": message},
                    ensure_ascii=False
                ),
                headers={
                    "Content-Type": "application/json"
                },
                timeout=30000
            )

            print("Discord 전송 상태:", response.status)

            if response.status not in [200, 204]:
                raise Exception(
                    f"Discord 전송 실패: {response.status}"
                )

        finally:
            request.dispose()


def main():

    today_text = datetime.now(KST).strftime("%Y%m%d")

    current_imax = get_imax_schedules()

    print()
    print("현재 IMAX 상영 개수:", len(current_imax))

    previous_imax = load_previous_imax()

    if previous_imax is None:

        print("첫 실행입니다. 현재 상태를 기준값으로 저장합니다.")

        save_imax(current_imax)

        print("기준값 저장 완료!")
        return

    previous_ids = {
        item["id"]
        for item in previous_imax
    }

    new_imax = [
        item
        for item in current_imax
        if (
            item["id"] not in previous_ids
            and item["date"] >= today_text
        )
    ]

    if new_imax:

        print("새로운 IMAX 상영 발견!")

        for item in new_imax:
            print(item)

        send_discord(new_imax)

    else:
        print("새로운 IMAX 상영이 없습니다.")

    save_imax(current_imax)

    print("IMAX 기록 저장 완료!")


if __name__ == "__main__":
    main()
