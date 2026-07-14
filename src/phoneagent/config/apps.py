"""App name to package name mapping for supported applications."""

APP_PACKAGES: dict[str, str] = {
    # Social & Messaging
    "微信": "com.tencent.mm",
    "QQ": "com.tencent.mobileqq",
    "微博": "com.sina.weibo",
    "企业微信": "com.tencent.wework",
    "WeCom": "com.tencent.wework",
    "脉脉": "com.taou.maimai",
    "陌陌": "com.immomo.momo",
    "Soul": "cn.soulapp.android",
    "soul": "cn.soulapp.android",
    # E-commerce
    "淘宝": "com.taobao.taobao",
    "京东": "com.jingdong.app.mall",
    "拼多多": "com.xunmeng.pinduoduo",
    "淘宝闪购": "com.taobao.taobao",
    "京东秒送": "com.jingdong.app.mall",
    "闲鱼": "com.taobao.idlefish",
    "咸鱼": "com.taobao.idlefish",
    "得物": "com.shizhuang.duapp",
    "唯品会": "com.achievo.vipshop",
    "苏宁易购": "com.suning.mobile.ebuy",
    "苏宁": "com.suning.mobile.ebuy",
    # Payment & Finance
    "支付宝": "com.eg.android.AlipayGphone",
    "Alipay": "com.eg.android.AlipayGphone",
    "云闪付": "com.unionpay",
    "中国银联": "com.unionpay",
    # Lifestyle & Social
    "小红书": "com.xingin.xhs",
    "豆瓣": "com.douban.frodo",
    "知乎": "com.zhihu.android",
    "百度": "com.baidu.searchbox",
    "百度App": "com.baidu.searchbox",
    # Maps & Navigation
    "高德地图": "com.autonavi.minimap",
    "百度地图": "com.baidu.BaiduMap",
    # Food & Services
    "美团": "com.sankuai.meituan",
    "大众点评": "com.dianping.v1",
    "饿了么": "me.ele",
    "肯德基": "com.yek.android.kfc.activitys",
    "瑞幸咖啡": "com.lucky.luckyclient",
    "瑞幸": "com.lucky.luckyclient",
    # Travel
    "携程": "ctrip.android.view",
    "铁路12306": "com.MobileTicket",
    "12306": "com.MobileTicket",
    "去哪儿": "com.Qunar",
    "去哪儿旅行": "com.Qunar",
    "滴滴出行": "com.sdu.didi.psnger",
    "滴滴": "com.sdu.didi.psnger",
    "飞猪": "com.taobao.trip",
    "飞猪旅行": "com.taobao.trip",
    "同程旅行": "com.tongcheng.android",
    "同程": "com.tongcheng.android",
    # Logistics
    "顺丰": "com.sf.activity",
    "顺丰速运": "com.sf.activity",
    "菜鸟": "com.cainiao.wireless",
    "菜鸟裹裹": "com.cainiao.wireless",
    # Video & Entertainment
    "哔哩哔哩": "tv.danmaku.bili",
    "B站": "tv.danmaku.bili",
    "bilibili": "tv.danmaku.bili",
    "抖音": "com.ss.android.ugc.aweme",
    "快手": "com.smile.gifmaker",
    "腾讯视频": "com.tencent.qqlive",
    "爱奇艺": "com.qiyi.video",
    "优酷视频": "com.youku.phone",
    "优酷": "com.youku.phone",
    "芒果TV": "com.hunantv.imgo.activity",
    "红果短剧": "com.phoenix.read",
    "西瓜视频": "com.ss.android.article.video",
    # Music & Audio
    "网易云音乐": "com.netease.cloudmusic",
    "QQ音乐": "com.tencent.qqmusic",
    "汽水音乐": "com.luna.music",
    "喜马拉雅": "com.ximalaya.ting.android",
    "酷狗音乐": "com.kugou.android",
    "酷狗": "com.kugou.android",
    "酷我音乐": "cn.kuwo.player",
    "酷我": "cn.kuwo.player",
    "咪咕音乐": "cmccwm.mobilemusic",
    "咪咕": "cmccwm.mobilemusic",
    # Reading
    "番茄小说": "com.dragon.read",
    "番茄免费小说": "com.dragon.read",
    "七猫免费小说": "com.kmxs.reader",
    # Productivity
    "飞书": "com.ss.android.lark",
    "钉钉": "com.alibaba.android.rimet",
    "DingTalk": "com.alibaba.android.rimet",
    "WPS": "cn.wps.moffice_eng",
    "WPS Office": "cn.wps.moffice_eng",
    "QQ邮箱": "com.tencent.androidqqmail",
    "百度网盘": "com.baidu.netdisk",
    "百度云": "com.baidu.netdisk",
    "夸克": "com.quark.browser",
    "夸克浏览器": "com.quark.browser",
    "力扣": "com.lingkou.leetcode",
    "LeetCode": "com.lingkou.leetcode",
    "leetcode": "com.lingkou.leetcode",
    "领扣": "com.lingkou.leetcode",
    "UC浏览器": "com.UCMobile",
    "UC": "com.UCMobile",
    "QQ浏览器": "com.tencent.mtt",
    # Photo & Design
    "美图秀秀": "com.mt.mtxx.mtxx",
    "美图": "com.mt.mtxx.mtxx",
    "醒图": "com.xt.retouch",
    # AI & Tools
    "豆包": "com.larus.nova",
    "Kimi": "com.moonshot.kimichat",
    "kimi": "com.moonshot.kimichat",
    # Health & Fitness
    "keep": "com.gotokeep.keep",
    "美柚": "com.lingan.seeyou",
    # News & Information
    "腾讯新闻": "com.tencent.news",
    "今日头条": "com.ss.android.article.news",
    # Real Estate
    "贝壳找房": "com.lianjia.beike",
    "安居客": "com.anjuke.android.app",
    # Finance
    "同花顺": "com.hexin.plat.android",
    # Games
    "星穹铁道": "com.miHoYo.hkrpg",
    "崩坏：星穹铁道": "com.miHoYo.hkrpg",
    "恋与深空": "com.papegames.lysk.cn",
    "AndroidSystemSettings": "com.android.settings",
    "Android System Settings": "com.android.settings",
    "Android  System Settings": "com.android.settings",
    "Android-System-Settings": "com.android.settings",
    "Settings": "com.android.settings",
    "设置": "com.android.settings",
    "系统设置": "com.android.settings",
    "AudioRecorder": "com.android.soundrecorder",
    "audiorecorder": "com.android.soundrecorder",
    "Bluecoins": "com.rammigsoftware.bluecoins",
    "bluecoins": "com.rammigsoftware.bluecoins",
    "Broccoli": "com.flauschcode.broccoli",
    "broccoli": "com.flauschcode.broccoli",
    "Booking.com": "com.booking",
    "Booking": "com.booking",
    "booking.com": "com.booking",
    "booking": "com.booking",
    "BOOKING.COM": "com.booking",
    "Chrome": "com.android.chrome",
    "chrome": "com.android.chrome",
    "Google Chrome": "com.android.chrome",
    "Clock": "com.android.deskclock",
    "clock": "com.android.deskclock",
    "Contacts": "com.android.contacts",
    "contacts": "com.android.contacts",
    "Duolingo": "com.duolingo",
    "duolingo": "com.duolingo",
    "Expedia": "com.expedia.bookings",
    "expedia": "com.expedia.bookings",
    "Files": "com.android.fileexplorer",
    "files": "com.android.fileexplorer",
    "File Manager": "com.android.fileexplorer",
    "file manager": "com.android.fileexplorer",
    "gmail": "com.google.android.gm",
    "Gmail": "com.google.android.gm",
    "GoogleMail": "com.google.android.gm",
    "Google Mail": "com.google.android.gm",
    "GoogleFiles": "com.google.android.apps.nbu.files",
    "googlefiles": "com.google.android.apps.nbu.files",
    "FilesbyGoogle": "com.google.android.apps.nbu.files",
    "GoogleCalendar": "com.google.android.calendar",
    "Google-Calendar": "com.google.android.calendar",
    "Google Calendar": "com.google.android.calendar",
    "google-calendar": "com.google.android.calendar",
    "google calendar": "com.google.android.calendar",
    "GoogleChat": "com.google.android.apps.dynamite",
    "Google Chat": "com.google.android.apps.dynamite",
    "Google-Chat": "com.google.android.apps.dynamite",
    "GoogleClock": "com.google.android.deskclock",
    "Google Clock": "com.google.android.deskclock",
    "Google-Clock": "com.google.android.deskclock",
    "GoogleContacts": "com.google.android.contacts",
    "Google-Contacts": "com.google.android.contacts",
    "Google Contacts": "com.google.android.contacts",
    "google-contacts": "com.google.android.contacts",
    "google contacts": "com.google.android.contacts",
    "GoogleDocs": "com.google.android.apps.docs.editors.docs",
    "Google Docs": "com.google.android.apps.docs.editors.docs",
    "googledocs": "com.google.android.apps.docs.editors.docs",
    "google docs": "com.google.android.apps.docs.editors.docs",
    "Google Drive": "com.google.android.apps.docs",
    "Google-Drive": "com.google.android.apps.docs",
    "google drive": "com.google.android.apps.docs",
    "google-drive": "com.google.android.apps.docs",
    "GoogleDrive": "com.google.android.apps.docs",
    "Googledrive": "com.google.android.apps.docs",
    "googledrive": "com.google.android.apps.docs",
    "GoogleFit": "com.google.android.apps.fitness",
    "googlefit": "com.google.android.apps.fitness",
    "GoogleKeep": "com.google.android.keep",
    "googlekeep": "com.google.android.keep",
    "GoogleMaps": "com.google.android.apps.maps",
    "Google Maps": "com.google.android.apps.maps",
    "googlemaps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "Google Play Books": "com.google.android.apps.books",
    "Google-Play-Books": "com.google.android.apps.books",
    "google play books": "com.google.android.apps.books",
    "google-play-books": "com.google.android.apps.books",
    "GooglePlayBooks": "com.google.android.apps.books",
    "googleplaybooks": "com.google.android.apps.books",
    "GooglePlayStore": "com.android.vending",
    "Google Play Store": "com.android.vending",
    "Google-Play-Store": "com.android.vending",
    "GoogleSlides": "com.google.android.apps.docs.editors.slides",
    "Google Slides": "com.google.android.apps.docs.editors.slides",
    "Google-Slides": "com.google.android.apps.docs.editors.slides",
    "GoogleTasks": "com.google.android.apps.tasks",
    "Google Tasks": "com.google.android.apps.tasks",
    "Google-Tasks": "com.google.android.apps.tasks",
    "Joplin": "net.cozic.joplin",
    "joplin": "net.cozic.joplin",
    "McDonald": "com.mcdonalds.app",
    "mcdonald": "com.mcdonalds.app",
    "Osmand": "net.osmand",
    "osmand": "net.osmand",
    "PiMusicPlayer": "com.Project100Pi.themusicplayer",
    "pimusicplayer": "com.Project100Pi.themusicplayer",
    "Quora": "com.quora.android",
    "quora": "com.quora.android",
    "Reddit": "com.reddit.frontpage",
    "reddit": "com.reddit.frontpage",
    "RetroMusic": "code.name.monkey.retromusic",
    "retromusic": "code.name.monkey.retromusic",
    "SimpleCalendarPro": "com.scientificcalculatorplus.simplecalculator.basiccalculator.mathcalc",
    "SimpleSMSMessenger": "com.simplemobiletools.smsmessenger",
    "Telegram": "org.telegram.messenger",
    "temu": "com.einnovation.temu",
    "Temu": "com.einnovation.temu",
    "Tiktok": "com.zhiliaoapp.musically",
    "tiktok": "com.zhiliaoapp.musically",
    "Twitter": "com.twitter.android",
    "twitter": "com.twitter.android",
    "X": "com.twitter.android",
    "VLC": "org.videolan.vlc",
    "WeChat": "com.tencent.mm",
    "wechat": "com.tencent.mm",
    "Whatsapp": "com.whatsapp",
    "WhatsApp": "com.whatsapp",
}



def _normalize_app_alias(value: str) -> str:
    """Normalize an app alias for tolerant lookup."""
    return "".join(str(value).strip().casefold().split())


_NORMALIZED_APP_PACKAGES: dict[str, str] = {}
for _alias, _package in APP_PACKAGES.items():
    _NORMALIZED_APP_PACKAGES.setdefault(_normalize_app_alias(_alias), _package)


def get_package_name(app_name: str) -> str | None:
    """Return a package name using exact or normalized alias matching.

    A raw Android package name is accepted as well, which makes Launch usable
    for apps that are not yet present in the built-in alias table.
    """
    value = str(app_name or "").strip()
    if not value:
        return None
    if value in APP_PACKAGES:
        return APP_PACKAGES[value]
    normalized = _normalize_app_alias(value)
    package = _NORMALIZED_APP_PACKAGES.get(normalized)
    if package:
        return package
    if _looks_like_package_name(value):
        return value
    return None


def _looks_like_package_name(value: str) -> bool:
    parts = value.split(".")
    if len(parts) < 2:
        return False
    return all(part and part.replace("_", "").isalnum() for part in parts)


def get_app_name(package_name: str) -> str | None:
    """Get a canonical configured alias from a package name."""
    for name, package in APP_PACKAGES.items():
        if package == package_name:
            return name
    return None


def list_supported_apps() -> list[str]:
    """Get all configured app aliases."""
    return list(APP_PACKAGES.keys())
