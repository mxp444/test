import re
import jieba
from typing import Dict, Tuple, List


class IncitementEvaluator:
    """煽动性评估器 - 检测文本的煽动性程度"""

    def __init__(self):
        # 初始化词库
        self._init_word_banks()

    def _init_word_banks(self):
        """初始化各类词库"""

        # 1. 极端情绪词库
        self.extreme_words = {
            # 绝对化词汇 (权重高)
            '绝对': 8, '一定': 7, '肯定': 6, '必然': 7, '必定': 7,
            '永远': 6, '彻底': 7, '完全': 5, '根本': 5, '丝毫': 6,
            '毫无疑问': 9, '毋庸置疑': 8, '百分之百': 9, '100%': 8,

            # 夸张形容词
            '疯狂': 7, '惊人': 6, '恐怖': 7, '可怕': 6, '震撼': 7,
            '惊天': 9, '骇人': 8, '爆炸性': 8, '颠覆性': 8, '奇迹': 7,
            '神话': 6, '传奇': 5, '史诗级': 7, '史无前例': 9, '前所未有': 8,

            # 煽动性动词
            '血洗': 9, '崩盘': 8, '暴跌': 7, '暴涨': 7, '抄底': 6,
            '逃顶': 6, '收割': 7, '跑路': 8, '暴雷': 8, '炸雷': 8,
            '爆雷': 8, '崩了': 7, '完了': 6, '废了': 6, '完了完了': 8,

            # 强调副词
            '极其': 6, '极为': 6, '无比': 7, '万分': 6, '超级': 5,
            '特别': 4, '非常': 4, '相当': 4, '十分': 4, '格外': 5,
            '尤其': 4, '尤其重要': 6, '至关重要': 7, '极其重要': 7
        }

        # 2. 稀缺性暗示词库
        self.scarcity_patterns = [
            # 时间紧迫类
            (r'仅剩?\s*\d+\s*(?:天|小时|分钟|秒|名额|位|个)', 30),  # 仅剩X天/名额
            (r'最后\s*\d+\s*(?:天|小时|分钟|机会|名额|位|个)', 30),  # 最后X天/名额
            (r'倒计时\s*\d+\s*(?:天|小时)', 25),  # 倒计时X天
            (r'限时|限量|限购', 20),  # 限时限量
            (r'截止到?\s*[今晚明天今天本月本年]?', 15),  # 截止时间
            (r'过期不候|错过不再|机不可失|失不再来', 25),  # 紧迫成语
            (r'即将(?:结束|关闭|截止|停止)', 20),  # 即将结束
            (r'马上(?:行动|开始|结束)', 15),  # 马上
            (r'立即|立刻|赶紧|赶快|尽快', 10),  # 立即行动

            # 数量稀缺类
            (r'售罄|售完|卖光|抢光|抢完', 25),  # 售罄
            (r'手慢无|手快有', 25),  # 手慢无
            (r'秒杀|疯抢|哄抢|抢购', 20),  # 抢购
            (r'限量\s*\d+\s*(?:份|个|套|件)', 30),  # 限量X份
            (r'仅此\s*\d+\s*(?:次|批|轮)', 25),  # 仅此X次
            (r'名额\s*有限|数量\s*有限|库存\s*有限', 20),  # 数量有限
            (r'先到先得|优先获取', 15),  # 先到先得
        ]

        # 3. 从众压力词库
        self.herd_patterns = [
            # 群体行为类
            (r'已有\s*\d+\s*(?:人|位|名|用户|投资者|参与者)', 30),  # 已有X人
            (r'\d+\s*(?:人|位|名|用户)\s*(?:参与|加入|购买|投资|关注)', 30),  # X人参与
            (r'(?:超|近|达|突破)\s*\d+\s*(?:万|亿)?\s*(?:人|用户|投资者)', 35),  # 超过X万人
            (r'(?:大家都在|人人都在|每个人都在)', 25),  # 大家都在
            (r'疯抢|哄抢|抢购|热抢', 25),  # 疯抢
            (r'人手(?:一份|一个|必备)', 20),  # 人手一份
            (r'刷屏|霸屏|霸榜', 25),  # 刷屏

            # 社会证明类
            (r'火爆|火热|热门|热潮', 15),  # 火爆
            (r'追捧|热捧|推崇|推荐', 15),  # 追捧
            (r'口碑(?:爆棚|炸裂|很好|不错)', 20),  # 口碑
            (r'网红|爆款|人气王|人气爆棚', 20),  # 网红爆款
            (r'(?:强烈|极力|疯狂)\s*(?:推荐|建议|安利)', 20),  # 强烈推荐

            # 趋势跟随类
            (r'跟上|跟紧|跟上节奏|跟上步伐', 15),  # 跟上
            (r'别掉队|别落后|别错过', 20),  # 别掉队
            (r'都在(?:做|买|投|看)', 20),  # 都在做
            (r'大势所趋|时代潮流|顺势而为', 15),  # 趋势
        ]

    def analyze_tone(self, text: str) -> Tuple[float, Dict]:
        """
        分析语气强烈程度

        Args:
            text: 输入文本

        Returns:
            score: 语气维度得分
            details: 详细分析结果
        """
        score = 0
        details = {
            'exclamation_count': 0,
            'extreme_words_found': [],
            'all_caps_ratio': 0,
            'repeated_punctuation': []
        }

        # 1. 感叹号检测
        exclamation_count = text.count('!') + text.count('！')
        details['exclamation_count'] = exclamation_count
        score += min(exclamation_count * 3, 15)  # 感叹号最多15分

        # 2. 连续标点检测 (!!!, ??, !? 等)
        repeated_punc = re.findall(r'[!?！？]{2,}', text)
        if repeated_punc:
            details['repeated_punctuation'] = repeated_punc
            score += len(repeated_punc) * 5  # 每组连续标点5分，最多10分
            score = min(score, 10)

        # 3. 全大写单词检测 (英文场景)
        words = text.split()
        all_caps_words = [w for w in words if w.isupper() and len(w) > 1]
        if all_caps_words:
            all_caps_ratio = len(all_caps_words) / len(words) if words else 0
            details['all_caps_ratio'] = all_caps_ratio
            score += min(all_caps_ratio * 50, 10)  # 全大写最多10分

        # 4. 极端词汇检测
        # 使用jieba分词
        words = jieba.lcut(text)
        extreme_found = []
        extreme_score = 0

        for word in words:
            if word in self.extreme_words:
                word_score = self.extreme_words[word]
                extreme_found.append(f"{word}({word_score})")
                extreme_score += word_score

        # 同时检查是否包含极端词汇作为子串（针对未登录词）
        for extreme_word, word_score in self.extreme_words.items():
            if extreme_word in text and extreme_word not in ''.join(words):
                extreme_found.append(f"{extreme_word}({word_score})")
                extreme_score += word_score

        details['extreme_words_found'] = extreme_found
        score += min(extreme_score, 35)  # 极端词汇最多35分

        # 总分封顶40分
        final_score = min(score, 40)
        details['raw_score'] = score
        details['final_score'] = final_score

        return final_score, details

    def analyze_scarcity(self, text: str) -> Tuple[float, Dict]:
        """
        分析稀缺性暗示

        Args:
            text: 输入文本

        Returns:
            score: 稀缺性维度得分
            details: 详细分析结果
        """
        score = 0
        details = {
            'matched_patterns': [],
            'urgency_phrases': [],
            'numbers_detected': []
        }

        # 检测所有稀缺性模式
        for pattern, base_score in self.scarcity_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                matched_text = match.group()
                details['matched_patterns'].append(f"{matched_text}({base_score})")

                # 提取数字进行加权
                numbers = re.findall(r'\d+', matched_text)
                if numbers:
                    num = int(numbers[0])
                    details['numbers_detected'].append(num)

                    # 根据数字大小调整分数
                    if '名额' in matched_text or '位' in matched_text or '个' in matched_text:
                        if num <= 5:  # 仅剩5个名额，紧迫感极强
                            score += base_score + 10
                        elif num <= 10:  # 仅剩10个名额
                            score += base_score + 5
                        else:
                            score += base_score
                    elif '天' in matched_text or '小时' in matched_text:
                        if num <= 1:  # 仅剩1天/小时
                            score += base_score + 15
                        elif num <= 3:  # 仅剩3天/小时
                            score += base_score + 8
                        elif num <= 7:  # 仅剩7天
                            score += base_score + 3
                        else:
                            score += base_score
                    else:
                        score += base_score
                else:
                    score += base_score

        # 检测常见的紧迫感短语（非结构化）
        urgency_phrases = [
            '再不行动', '再不考虑', '再犹豫', '错过今天', '机会难得',
            '不容错过', '千载难逢', '难得一见', '稍纵即逝', '转瞬即逝'
        ]

        for phrase in urgency_phrases:
            if phrase in text:
                details['urgency_phrases'].append(phrase)
                score += 10

        # 总分封顶30分
        final_score = min(score, 30)
        details['raw_score'] = score
        details['final_score'] = final_score

        return final_score, details

    def analyze_herd(self, text: str) -> Tuple[float, Dict]:
        """
        分析从众压力

        Args:
            text: 输入文本

        Returns:
            score: 从众压力维度得分
            details: 详细分析结果
        """
        score = 0
        details = {
            'matched_patterns': [],
            'numbers_detected': [],
            'social_proof_phrases': []
        }

        # 检测所有从众压力模式
        for pattern, base_score in self.herd_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                matched_text = match.group()
                details['matched_patterns'].append(f"{matched_text}({base_score})")

                # 提取数字进行加权
                numbers = re.findall(r'\d+', matched_text)
                if numbers:
                    num = int(numbers[0])
                    details['numbers_detected'].append(num)

                    # 根据参与人数调整分数
                    if '万' in matched_text or '亿' in matched_text or num >= 10000:
                        score += base_score + 15  # 万人参与，加分更多
                    elif num >= 1000:
                        score += base_score + 10  # 千人参与
                    elif num >= 100:
                        score += base_score + 5  # 百人参与
                    else:
                        score += base_score
                else:
                    score += base_score

        # 检测社交证明短语
        social_proof_phrases = [
            '邻居都', '同事都', '朋友都', '大家都在', '所有人都在',
            '大家都说', '都说好', '一致好评', '公认', '众所周知'
        ]

        for phrase in social_proof_phrases:
            if phrase in text:
                details['social_proof_phrases'].append(phrase)
                score += 8

        # 检测权威背书类
        authority_phrases = [
            '专家推荐', '权威认证', '官方认可', '机构背书',
            '大V推荐', 'KOL推荐', '网红同款', '明星同款'
        ]

        for phrase in authority_phrases:
            if phrase in text:
                details['social_proof_phrases'].append(f"权威背书:{phrase}")
                score += 12

        # 总分封顶30分
        final_score = min(score, 30)
        details['raw_score'] = score
        details['final_score'] = final_score

        return final_score, details

    def evaluate(self, text: str) -> Dict:
        """
        综合评估文本的煽动性程度

        Args:
            text: 输入文本

        Returns:
            dict: 包含总分和各维度得分的评估结果
        """
        # 分析各维度
        tone_score, tone_details = self.analyze_tone(text)
        scarcity_score, scarcity_details = self.analyze_scarcity(text)
        herd_score, herd_details = self.analyze_herd(text)

        # 计算总分 (各维度满分分别为40,30,30，总分100)
        total_score = tone_score + scarcity_score + herd_score

        # 确定风险等级
        if total_score >= 80:
            risk_level = "极高风险"
            risk_desc = "文本具有极强的煽动性，可能涉及诈骗或恶意营销"
        elif total_score >= 60:
            risk_level = "高风险"
            risk_desc = "文本煽动性明显，需要警惕可能的误导"
        elif total_score >= 40:
            risk_level = "中等风险"
            risk_desc = "文本具有一定煽动性，建议谨慎对待"
        elif total_score >= 20:
            risk_level = "低风险"
            risk_desc = "文本煽动性较弱，基本属于正常表达"
        else:
            risk_level = "无风险"
            risk_desc = "文本客观理性，无明显煽动性"

        # 构建返回结果
        result = {
            'text': text,
            'total_score': total_score,
            'risk_level': risk_level,
            'risk_description': risk_desc,
            'dimensions': {
                'tone': {
                    'score': tone_score,
                    'max_score': 40,
                    'percentage': round(tone_score / 40 * 100, 1),
                    'details': tone_details
                },
                'scarcity': {
                    'score': scarcity_score,
                    'max_score': 30,
                    'percentage': round(scarcity_score / 30 * 100, 1),
                    'details': scarcity_details
                },
                'herd': {
                    'score': herd_score,
                    'max_score': 30,
                    'percentage': round(herd_score / 30 * 100, 1),
                    'details': herd_details
                }
            },
            'recommendation': self._get_recommendation(total_score, tone_score, scarcity_score, herd_score)
        }

        return result

    def _get_recommendation(self, total: float, tone: float, scarcity: float, herd: float) -> str:
        """根据得分生成建议"""
        if total >= 80:
            return "立即标记为高风险内容，建议人工复核并考虑屏蔽"
        elif total >= 60:
            return "标记为需关注内容，加强监控频率"
        elif total >= 40:
            return "常规监控，关注传播情况"
        else:
            return "正常内容，保持常规监控"

    def batch_evaluate(self, texts: List[str]) -> List[Dict]:
        """批量评估多个文本"""
        return [self.evaluate(text) for text in texts]


if __name__ == "__main__":

    # 创建评估器
    evaluator = IncitementEvaluator()

    # 测试案例  # 案例1：典型的煽动性营销文本（高风险）
    test_case = """        
        【紧急通知】最后3小时！仅剩5个名额！已有18923人抢购！
        绝对震撼！史无前例的优惠！再不行动就永远错过了！
        大家都在疯抢，你还在等什么？手慢无！！！！
        """
#         # 案例2：金融投资类煽动性文本（高风险）
#         """
#         崩盘了！暴跌了！千载难逢的抄底机会！
# 　　　　仅此一次，错过再等十年！目前已有超过5万投资者火速入场！
#         内幕消息：主力资金正在疯狂买入，赶紧跟上！！！
#         """
#
#         # 案例3：中等风险的文本
#         """
#         本次优惠活动还剩最后两天，已有300多人参与。
#         机会难得，建议抓紧时间考虑。名额有限，先到先得。
#         """
#
#         # 案例4：正常文本（低风险）
#         """
#         根据最新市场数据，本次理财产品年化收益率在3%-4%之间，
#         投资有风险，请根据自身情况谨慎决策。市场有风险，投资需谨慎。
#         """
#
#         # 案例5：多个煽动性元素组合
#         """
#         【限时抢购】最后1天！仅剩3个VIP名额！
#         绝对内部福利！已经有25678人领取！
#         疯抢中！手慢无！再犹豫就没了！！！！！
#         专家强烈推荐，口碑爆棚！
#         """

    result = evaluator.evaluate(test_case)

    print(f"总分: {result['total_score']}/100")
    print(f"风险等级: {result['risk_level']}")
    print(f"风险描述: {result['risk_description']}")
    print("\n各维度得分:")
    print(f"  - 语气强烈程度: {result['dimensions']['tone']['score']}/40 "
          f"({result['dimensions']['tone']['percentage']}%)")
    print(f"  - 稀缺性暗示: {result['dimensions']['scarcity']['score']}/30 "
          f"({result['dimensions']['scarcity']['percentage']}%)")
    print(f"  - 从众压力: {result['dimensions']['herd']['score']}/30 "
          f"({result['dimensions']['herd']['percentage']}%)")
    print(f"\n建议: {result['recommendation']}")

    if result['total_score'] >= 60:  # 高风险才打印详细
        print("\n【详细检测结果】")
        if result['dimensions']['tone']['details']['extreme_words_found']:
            print(f"检测到的极端词: {result['dimensions']['tone']['details']['extreme_words_found']}")
        if result['dimensions']['scarcity']['details']['matched_patterns']:
            print(f"检测到的稀缺性模式: {result['dimensions']['scarcity']['details']['matched_patterns']}")
        if result['dimensions']['herd']['details']['matched_patterns']:
            print(f"检测到的从众压力模式: {result['dimensions']['herd']['details']['matched_patterns']}")
