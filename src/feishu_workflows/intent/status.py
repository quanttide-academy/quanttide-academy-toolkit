"""话题状态：库里存英文，给用户看的文字用中文。"""

ZH = {
    "pending": "待确认",
    "written": "已写入",
    "rejected": "已否决",
    "fyi": "仅知悉",
    "following": "已在跟进",
    "closed": "已结束",
}


def label(status):
    return ZH.get(status, status or "未知")
