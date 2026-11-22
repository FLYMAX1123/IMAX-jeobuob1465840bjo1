
import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
    print("Playwright Chromium 방식")
    print("=" * 40)

    imax_list = []

    today = datetime.now(KST).date()

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul"
        )

        try:

            page = context.new_page()

            print("CGV 예매 페이지 접속 중...")

            page_response = page.goto(
                BOOKING_PAGE,
                wait_until="domcontentloaded",
                timeout=60000
            )

            if page_response is None:
                raise Exception("CGV 페이지 응답이 없습니다.")

            print(
                "CGV 페이지 상태:",
                page_response.status
            )

            if page_response.status != 200:
                raise Exception(
                    f"CGV 페이지 접속 실패: {page_response.status}"
                )

            print("브라우저 세션 준비 완료!")

            for i in range(14):

                target_date = today + timedelta(days=i)

                date_text = target_date.strftime("%Y%m%d")

                print()
                print(f"{date_text} 조회 중...")

                response = context.request.get(
                    API_URL,
                    params={
                        "coCd": "A420",
                        "siteNo": THEATER_CODE,
                        "scnYmd": date_text,
                        "rtctlScopCd": "08"
                    },
                    headers={
                        "Accept": "application/json, text/plain, */*",
                        "Accept-Language": "ko-KR,ko;q=0.9",
                        "Referer": BOOKING_PAGE
                    },
                    timeout=30000
                )

                print(
                    "API 상태:",
                    response.status
                )

                if response.status != 200:
                    raise Exception(
                        f"{date_text} API 조회 실패: "
                        f"{response.status}"
                    )

                data = response.json()

                if data.get("statusCode") not in (0, "0"):
                    raise Exception(
                        f"CGV API 오류: {data}"
                    )

                schedules = data.get("data") or []

                for schedule in schedules:

                    screen_name = (
                        schedule.get("scnsNm") or ""
                    )

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

                    start_time = (
                        schedule.get("scnsrtTm") or ""
                    )

                    schedule_id = (
                        f"{date_text}|"
                        f"{movie_name}|"
                        f"{screen_name}|"
                        f"{start_time}"
                    )

                    imax_info = {
                        "id": schedule_id,
                        "date": date_text,
                        "movie": movie_name,
                        "screen": (
                            display_screen_name or screen_name
                        ),
                        "time": start_time
                    }

                    imax_list.append(imax_info)

                    print("IMAX 발견:", imax_info)

            unique_imax = {
                item["id"]: item
                for item in imax_list
            }

            return list(unique_imax.values())

        finally:

            context.close()
            browser.close()


def load_previous_imax():

    if not os.path.exists(STATE_FILE):
        return None

    with open(
        STATE_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def save_imax(imax_list):

    with open(
        STATE_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            imax_list,
            file,
            ensure_ascii=False,
            indent=2
        )


def send_discord(new_imax):

    if not WEBHOOK_URL:
        raise Exception(
            "DISCORD_WEBHOOK_URL이 없습니다."
        )

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
        "🔔 CGV 광교 IMAX 신규 상영이 발견되었습니다!"
    )

    from playwright.sync_api import sync_playwright

    # Discord 전송은 일반 HTTPS 요청으로 처리
    import urllib.request

    request = urllib.request.Request(
        WEBHOOK_URL,
        data=json.dumps({
            "content": message
        }).encode("utf-8"),
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(
        request,
        timeout=30
    ) as response:

        print(
            "Discord 전송 상태:",
            response.status
        )

        if response.status not in (200, 204):
            raise Exception("Discord 전송 실패")


def main():

    today = datetime.now(KST).date()

    today_text = today.strftime("%Y%m%d")

    # CGV 조회가 실패하면 여기서 중단되므로
    # 기존 last_imax.json은 그대로 유지됨
    current_imax = get_imax_schedules()

    print()
    print("현재 IMAX 개수:", len(current_imax))

    previous_imax = load_previous_imax()

    # 최초 실행은 기준값만 저장
    if previous_imax is None:

        print("첫 실행입니다.")
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

        print("새로운 IMAX 발견!")

        for item in new_imax:
            print(item)

        send_discord(new_imax)

    else:

        print("새로운 IMAX 상영이 없습니다.")

    # 조회와 알림이 모두 정상적으로 끝난 뒤 저장
    save_imax(current_imax)

    print("IMAX 기록 저장 완료!")


if __name__ == "__main__":
    main()
