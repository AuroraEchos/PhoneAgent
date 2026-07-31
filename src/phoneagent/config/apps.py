from typing import Optional

APP_PACKAGES: dict[str, str] = {
    # ============================================================
    # Social & Communication 社交通信
    # ============================================================
    "微信": "com.tencent.mm",
    "微信聊天": "com.tencent.mm",
    "WeChat": "com.tencent.mm",
    "wechat": "com.tencent.mm",
    "QQ": "com.tencent.mobileqq",
    "TIM": "com.tencent.tim",
    "QQ空间": "com.qzone",
    "企业微信": "com.tencent.wework",
    "微信企业版": "com.tencent.wework",
    "钉钉": "com.alibaba.android.rimet",
    "DingTalk": "com.alibaba.android.rimet",
    "飞书": "com.ss.android.lark",
    "Lark": "com.ss.android.lark",
    "微博": "com.sina.weibo",
    "小红书": "com.xingin.xhs",
    "知乎": "com.zhihu.android",
    "豆瓣": "com.douban.frodo",
    "脉脉": "com.taou.maimai",
    "Soul": "cn.soulapp.android",
    "BOSS直聘": "com.hpbr.bosszhipin",
    # ============================================================
    # Payment & Finance 支付金融
    # ============================================================
    "支付宝": "com.eg.android.AlipayGphone",
    "支付宝钱包": "com.eg.android.AlipayGphone",
    "Alipay": "com.eg.android.AlipayGphone",
    "云闪付": "com.unionpay",
    "中国银联": "com.unionpay",
    "招商银行": "cmb.pb",
    "中国银行": "com.chinamworld.main",
    "工商银行": "com.icbc",
    "建设银行": "com.ccb.mobilebank",
    "平安银行": "com.pingan.pabank",
    "交通银行": "com.bankcomm.Bankcomm",
    "同花顺": "com.hexin.plat.android",
    # ============================================================
    # E-commerce 电商购物
    # ============================================================
    "淘宝": "com.taobao.taobao",
    "淘宝网": "com.taobao.taobao",
    "京东": "com.jingdong.app.mall",
    "拼多多": "com.xunmeng.pinduoduo",
    "闲鱼": "com.taobao.idlefish",
    "咸鱼": "com.taobao.idlefish",
    "得物": "com.shizhuang.duapp",
    "唯品会": "com.achievo.vipshop",
    "苏宁易购": "com.suning.mobile.ebuy",
    "京东金融": "com.jd.jrapp",
    "山姆": "cn.samsclub.app",
    "山姆会员商店": "cn.samsclub.app",
    "朴朴": "com.pupumall.customer",
    "朴朴超市": "com.pupumall.customer",
    # ============================================================
    # Food & Local Services 生活服务
    # ============================================================
    "美团": "com.sankuai.meituan",
    "美团外卖": "com.sankuai.meituan",
    "大众点评": "com.dianping.v1",
    "饿了么": "me.ele",
    "盒马": "com.wudaokou.hippo",
    "叮咚买菜": "com.yaya.zone",
    "肯德基": "com.yek.android.kfc.activitys",
    "瑞幸": "com.lucky.luckyclient",
    "瑞幸咖啡": "com.lucky.luckyclient",
    "库迪咖啡": "com.kudi.coffee",
    "Keep": "com.gotokeep.keep",
    # ============================================================
    # Maps Travel Transportation 地图出行
    # ============================================================
    "高德地图": "com.autonavi.minimap",
    "高德": "com.autonavi.minimap",
    "百度地图": "com.baidu.BaiduMap",
    "滴滴": "com.sdu.didi.psnger",
    "滴滴出行": "com.sdu.didi.psnger",
    "哈啰出行": "com.jingyao.easybike",
    "曹操出行": "com.caocaokeji.user",
    "铁路12306": "com.MobileTicket",
    "12306": "com.MobileTicket",
    "携程": "ctrip.android.view",
    "去哪儿": "com.Qunar",
    "飞猪": "com.taobao.trip",
    "同程旅行": "com.tongcheng.android",
    # ============================================================
    # Logistics 快递物流
    # ============================================================
    "顺丰": "com.sf.activity",
    "顺丰速运": "com.sf.activity",
    "菜鸟": "com.cainiao.wireless",
    "菜鸟裹裹": "com.cainiao.wireless",
    "京东物流": "com.jingdong.jdma",
    "中通": "com.zto.rec",
    "圆通": "com.yto.client",
    "申通": "com.sto.express",
    "韵达": "com.yunda.app",
    # ============================================================
    # Video Entertainment & Game 影音娱乐 & 游戏
    # ============================================================
    "抖音": "com.ss.android.ugc.aweme",
    "短视频": "com.ss.android.ugc.aweme",
    "快手": "com.smile.gifmaker",
    "哔哩哔哩": "tv.danmaku.bili",
    "B站": "tv.danmaku.bili",
    "腾讯视频": "com.tencent.qqlive",
    "爱奇艺": "com.qiyi.video",
    "优酷": "com.youku.phone",
    "芒果TV": "com.hunantv.imgo.activity",
    "西瓜视频": "com.ss.android.article.video",
    "虎牙": "com.duowan.kiwi",
    "斗鱼": "air.tv.douyu.android",
    "全民K歌": "com.tencent.karaoke",
    "王者荣耀": "com.tencent.tmgp.sgame",
    "和平精英": "com.tencent.tmgp.pubgmhd",
    "原神": "com.miHoYo.GenshinImpact",
    # ============================================================
    # Music & Reading 音乐阅读
    # ============================================================
    "网易云音乐": "com.netease.cloudmusic",
    "QQ音乐": "com.tencent.qqmusic",
    "酷狗音乐": "com.kugou.android",
    "酷我音乐": "cn.kuwo.player",
    "喜马拉雅": "com.ximalaya.ting.android",
    "番茄小说": "com.dragon.read",
    "七猫小说": "com.kmxs.reader",
    # ============================================================
    # Office & Productivity 办公效率
    # ============================================================
    "WPS": "cn.wps.moffice_eng",
    "WPS Office": "cn.wps.moffice_eng",
    "QQ邮箱": "com.tencent.androidqqmail",
    "百度网盘": "com.baidu.netdisk",
    "夸克": "com.quark.browser",
    "QQ浏览器": "com.tencent.mtt",
    "UC浏览器": "com.UCMobile",
    "印象笔记": "com.yxbj",
    "腾讯文档": "com.tencent.docs",
    "石墨文档": "com.shimo.im",
    # ============================================================
    # Education 教育学习
    # ============================================================
    "学习通": "com.chaoxing.mobile",
    "作业帮": "com.baidu.homework",
    "小猿搜题": "com.fenbi.android.leo",
    "腾讯课堂": "com.tencent.edu",
    "力扣": "com.lingkou.leetcode",
    "LeetCode": "com.lingkou.leetcode",
    # ============================================================
    # AI Tools 人工智能
    # ============================================================
    "豆包": "com.larus.nova",
    "Kimi": "com.moonshot.kimichat",
    "通义": "com.aliyun.tongyi",
    "千问": "com.aliyun.tongyi",
    "文心一言": "com.baidu.newapp",
    "文心": "com.baidu.newapp",
    "DeepSeek": "com.deepseek.chat",
    "智谱清言": "com.zhipu.zhipuchat",
    # ============================================================
    # App Market 应用市场
    # ============================================================
    "应用宝": "com.tencent.android.qqdownloader",
    "小米应用商店": "com.xiaomi.market",
    "华为应用市场": "com.huawei.appmarket",
    "OPPO应用商店": "com.oppo.market",
    "vivo应用商店": "com.bbk.appstore",
    "酷安": "com.coolapk.market",
    # ============================================================
    # System Apps 系统应用
    # ============================================================
    "设置": "com.android.settings",
    "系统设置": "com.android.settings",
    "相机": "com.android.camera",
    "Camera": "com.android.camera",
    "图库": "com.android.gallery3d",
    "照片": "com.android.gallery3d",
    "联系人": "com.android.contacts",
    "电话": "com.android.dialer",
    "短信": "com.android.mms",
    "文件管理": "com.android.fileexplorer",
    "时钟": "com.android.deskclock",
    # ============================================================
    # Global Compatibility 国际兼容
    # ============================================================
    "Chrome": "com.android.chrome",
    "Gmail": "com.google.android.gm",
    "Google Maps": "com.google.android.apps.maps",
    "WhatsApp": "com.whatsapp",
    "Telegram": "org.telegram.messenger",
}


def _normalize_app_alias(value: str) -> str:
    """Normalize an app alias for tolerant lookup.
    Strip whitespace, lowercase, remove all internal whitespace.
    Example: "瑞幸 咖啡" -> "瑞幸咖啡"
    """
    return "".join(str(value).strip().casefold().split())


# Normalized alias -> package name mapping
# Warning: if two aliases collide after normalization, only the first one is kept
_NORMALIZED_APP_PACKAGES: dict[str, str] = {}
# Canonical package -> primary app name (first encountered alias as standard name)
_CANONICAL_PACKAGE_TO_NAME: dict[str, str] = {}

for alias, pkg in APP_PACKAGES.items():
    norm_key = _normalize_app_alias(alias)
    if norm_key not in _NORMALIZED_APP_PACKAGES:
        _NORMALIZED_APP_PACKAGES[norm_key] = pkg
    # Store the FIRST alias as canonical display name for this package
    if pkg not in _CANONICAL_PACKAGE_TO_NAME:
        _CANONICAL_PACKAGE_TO_NAME[pkg] = alias


def _looks_like_package_name(value: str) -> bool:
    """Simple heuristic to judge whether input string is Android package name format."""
    parts = value.split(".")
    if len(parts) < 2:
        return False
    return all(part and part.replace("_", "").isalnum() for part in parts)


def get_package_name(app_name: str) -> Optional[str]:
    """
    Resolve input name to Android package name.
    Matching priority:
        1. Exact raw alias match
        2. Normalized tolerant alias match
        3. Directly return input if string matches package name format
    Return None if cannot resolve.
    """
    value = str(app_name or "").strip()
    if not value:
        return None

    # Exact match first
    if value in APP_PACKAGES:
        return APP_PACKAGES[value]

    normalized = _normalize_app_alias(value)
    pkg = _NORMALIZED_APP_PACKAGES.get(normalized)
    if pkg:
        return pkg

    # Treat raw input as package name
    if _looks_like_package_name(value):
        return value

    return None


def get_canonical_app_name(package_name: str) -> Optional[str]:
    """
    Get canonical display name from package name.
    Returns the FIRST registered alias as standard name.
    Return None when package not present in alias table.
    """
    return _CANONICAL_PACKAGE_TO_NAME.get(package_name)


def list_supported_apps() -> list[str]:
    """Get all defined app aliases (raw keys)."""
    return list(APP_PACKAGES.keys())


def list_canonical_app_mapping() -> dict[str, str]:
    """Return package -> standard app name mapping for UI display."""
    return _CANONICAL_PACKAGE_TO_NAME.copy()
