import numpy as np
from gensim.models import KeyedVectors
import jieba
from pathlib import Path

class Risk_factor():
    def __init__(self):
        path = Path(__file__).resolve().parent / "sgns.financial.word"
        self.WORD2VEC_PATH = str(path)
        self.SIMILARITY_THRESHOLD = 0.40  # 略微降低阈值以适应旧词库
        self.category_seeds = {
            # 1. 保本无风险虚假承诺类
            "保本无风险虚假承诺类": [
                "保本", "保息", "零风险", "无风险", "保证", "担保",
                "保底", "本金", "安全", "稳赚", "盈利", "收益",
                "保障", "本息", "兑付", "风险", "损失", "赔偿"
            ],

            # 2. 超高收益诱惑类
            "超高收益诱惑类": [
                "暴利", "翻倍", "高回报", "高收益", "收益", "回报",
                "利润", "盈利", "获利", "高额", "增值", "升值",
                "财富", "自由", "投资", "理财", "年化", "收益率"
            ],

            # 3. 传销拉人头层级返利类
            "传销拉人头层级返利类": [
                "下线", "上线", "层级", "代理", "分销", "返利",
                "分红", "奖励", "推荐", "介绍", "团队", "发展",
                "会员", "等级", "提成", "佣金", "裂变", "渠道"
            ],

            # 4. 内幕消息违规荐股类
            "内幕消息违规荐股类": [
                "内幕", "内部", "消息", "情报", "股票", "股市",
                "证券", "投资", "行情", "分析", "预测", "推荐",
                "机构", "主力", "庄家", "建仓", "拉升", "涨停"
            ],

            # 5. 紧迫饥饿营销逼单类
            "紧迫饥饿营销逼单类": [
                "限时", "限量", "最后", "机会", "截止", "立即",
                "马上", "赶快", "赶紧", "错过", "失去", "紧急",
                "迫切", "迅速", "即将", "结束", "关闭", "倒计时"
            ],

            # 6. 虚假资质权威背书类
            "虚假资质权威背书类": [
                "监管", "批准", "合法", "合规", "官方", "政府",
                "国家", "银行", "金融", "机构", "权威", "认证",
                "证书", "牌照", "资质", "备案", "托管", "存管"
            ],

            # 7. 虚拟货币/数字资产诈骗类 (旧词库没有比特币，用通用词代替)
            "虚拟货币数字资产诈骗类": [
                "货币", "数字", "虚拟", "资产", "交易", "市场",
                "投资", "投机", "外汇", "期货", "杠杆", "风险",
                "金融", "网络", "电子", "支付", "结算", "跨境"
            ],

            # 8. 征信修复/贷款诈骗类
            "征信修复贷款诈骗类": [
                "贷款", "借款", "信用", "征信", "逾期", "还款",
                "利息", "利率", "抵押", "担保", "借款", "资金",
                "周转", "银行", "信用卡", "办理", "申请", "额度"
            ],

            # 9. 私域引流联系方式类 (旧词库没有vx，用全称)
            "私域引流联系方式类": [
                "微信", "联系", "电话", "手机", "号码", "咨询",
                "客服", "顾问", "经理", "添加", "好友", "私信",
                "留言", "扫描", "二维码", "链接", "网站", "平台"
            ],

            # 10. 虚假造势从众诱导类
            "虚假造势从众诱导类": [
                "火爆", "抢购", "热销", "万人", "众多", "参与",
                "成功", "案例", "真实", "有效", "好评", "反馈",
                "信任", "信赖", "选择", "跟随", "跟风", "大众"
            ],

            # 11. 非法外盘/跨境金融交易类
            "非法外盘跨境金融交易类": [
                "外汇", "期货", "黄金", "原油", "国际", "全球",
                "境外", "海外", "交易", "市场", "杠杆", "保证金",
                "经纪", "代理", "平台", "投资", "金融", "套利"
            ],

            # 12. 养老金融诈骗类 (大幅简化，只剩核心词)
            "养老金融诈骗类": [
                "养老", "老年", "健康", "医疗", "养生", "服务",
                "公寓", "住宅", "社区", "投资", "理财", "保险",
                "产品", "项目", "福利", "补贴", "保障", "生活"
            ],

            # 13. 资金盘/庞氏骗局特征类
            "资金盘庞氏骗局特征类": [
                "资金", "盘", "理财", "投资", "项目", "平台",
                "崩盘", "跑路", "关闭", "提现", "冻结", "账户",
                "重启", "制度", "模式", "循环", "复利", "拆分"
            ],

            # 14. 代客理财违规操作类
            "代客理财违规操作类": [
                "代理", "委托", "理财", "投资", "操作", "交易",
                "账户", "资金", "托管", "管理", "顾问", "指导",
                "操盘", "分成", "收益", "亏损", "风险", "承诺"
            ],

            # 15. 数字藏品/元宇宙金融骗局类 (旧词库没有，用文创/科技概念代替)
            "数字藏品元宇宙金融骗局类": [
                "数字", "文化", "创意", "产品", "艺术品", "收藏",
                "价值", "增值", "升值", "投资", "科技", "网络",
                "虚拟", "现实", "游戏", "道具", "资产", "版权"
            ],

            # 16. 股票/期货配资违规交易类
            "股票期货配资违规交易类": [
                "股票", "期货", "配资", "杠杆", "资金", "放大",
                "投资", "交易", "风险", "收益", "账户", "操作",
                "利息", "费用", "平台", "机构", "证券", "金融"
            ]
        }
        print(f"正在加载词向量模型: {path} ...")
        try:
            self.model = KeyedVectors.load_word2vec_format(str(path), binary=False)
            print(f"模型加载成功！词表大小: {len(self.model.key_to_index)}")
        except Exception as e:
            raise RuntimeError(f"词向量模型加载失败: {e}") from e

        self.category_vectors = {}
        print("\n正在构建类别向量...")
        for category, seeds in self.category_seeds.items():
            valid_seeds = [seed for seed in seeds if seed in self.model]
            if valid_seeds:
                vectors = [self.model[seed] for seed in valid_seeds]
                self.category_vectors[category] = np.mean(vectors, axis=0)
                print(f"[OK] {category}: {len(valid_seeds)}/{len(seeds)}")
            else:
                print(f"[WARN] {category} 构建失败")
        print(f"\n成功构建 {len(self.category_vectors)} 个类别\n")

    def classify_word(self, word):
        """判断单个词的风险类别"""
        if word not in self.model:
            return None, 0.0

        word_vector = self.model[word]
        similarities = {}

        for category, cat_vector in self.category_vectors.items():
            norm_word = np.linalg.norm(word_vector)
            norm_cat = np.linalg.norm(cat_vector)
            if norm_word == 0 or norm_cat == 0:
                cos_sim = 0.0
            else:
                cos_sim = np.dot(word_vector, cat_vector) / (norm_word * norm_cat)
            similarities[category] = cos_sim

        best_category = max(similarities, key=similarities.get)
        best_score = similarities[best_category]

        if best_score >= self.SIMILARITY_THRESHOLD:
            return best_category, best_score
        else:
            return None, best_score

    def analyze_text(self, text):
        """分析完整文本"""
        words = jieba.lcut(text)

        # 初始化结果
        result = {cat: [] for cat in self.category_vectors.keys()}
        result["未分类"] = []

        for word in words:
            if len(word) < 2:  # 过滤单字
                continue

            category, score = self.classify_word(word)
            if category:
                # 简单去重
                if not any(item['word'] == word for item in result[category]):
                    result[category].append({"word": word, "score": round(score, 4)})
            else:
                if word in self.model:
                    result["未分类"].append({"word": word, "score": round(score, 4)})

        # 统计
        summary = {}
        total_risk = 0
        for cat in self.category_vectors.keys():
            count = len(result[cat])
            summary[cat] = count
            total_risk += count
        summary["总风险词数"] = total_risk

        sorted_summary = dict(sorted(summary.items(), key=lambda item: item[1], reverse=True))
        return result, sorted_summary


if __name__ == "__main__":
    model = Risk_factor()

    demo_text = "最后机会！内部渠道保本保息高收益理财，年化收益可观，轻松赚钱不是梦！赶紧联系我们，推荐朋友发展下线还有额外返利分红，错过不再有！"

    print(f"【检测文本】: {demo_text}\n")
    result, summary = model.analyze_text(demo_text)
    print("--- 风险统计 ---")

    for k, v in summary.items():
        if v > 0 or "总风险" in k:
            print(f"{k}: {v}")

    print("\n--- 详细命中词 ---")
    for cat, words in result.items():
        if words and cat != "未分类":
            print(f"\n[{cat}]")
            for w in words:
                print(f"  - {w['word']} ({w['score']})")
    # --- 风险统计 - --
    # 总风险词数: 25
    # 传销拉人头层级返利类: 6
    # 超高收益诱惑类: 4
    # 紧迫饥饿营销逼单类: 4
    # 虚假造势从众诱导类: 3
    # 保本无风险虚假承诺类: 2
    # 内幕消息违规荐股类: 2
    # 私域引流联系方式类: 2
    # 养老金融诈骗类: 1
    # 代客理财违规操作类: 1
    #
    # --- 详细命中词 - --
    #
    # [保本无风险虚假承诺类]
    # - 保本(0.5888000130653381)
    # - 保息(0.669700026512146)
    #
    # [超高收益诱惑类]
    # - 收益(0.7218000292778015)
    # - 年化(0.569100022315979)
    # - 可观(0.5435000061988831)
    # - 赚钱(0.5141000151634216)
    #
    # [传销拉人头层级返利类]
    # - 内部(0.40549999475479126)
    # - 渠道(0.6376000046730042)
    # - 下线(0.44589999318122864)
    # - 额外(0.4153999984264374)
    # - 返利(0.6069999933242798)
    # - 分红(0.42289999127388)
