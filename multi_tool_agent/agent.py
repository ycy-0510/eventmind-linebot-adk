import datetime
from zoneinfo import ZoneInfo

timezone_str = "Asia/Taipei"

def get_current_time() -> str:
    """
    取得現在的時間，用來解析如『明天』、『下週一』等模糊時間。

    Returns:
        str: ISO 格式時間字串（例如 '2025-06-15T20:00:00+08:00'）
    """
    tz = ZoneInfo(timezone_str)
    current_time = datetime.datetime.now(tz)
    return current_time.isoformat()


def parse_event(title: str, date: str, time: str, note: str = "") -> dict:
    """
    解析事件資訊，結構化活動內容。

    Args:
        title (str): 活動標題
        date (str): 活動日期（格式：YYYY-MM-DD）
        time (str): 活動時間（格式：HH:mm）
        note (str): 備註（可省略）

    Returns:
        dict: 回傳結構化事件 JSON，外層含有 type = "Event"
    """
    return {
        "type": "Event",
        "data": {
            "title": title,
            "date": date,
            "time": time,
            "note": note
        }
    }
