# LLM 回复专业度升级方案

诊断:回复不够专业不是模型问题,而是 (1) 数据颗粒度不足 (2) 输出模板过窄
(3) 缺少领域知识锚点 (4) 无历史对比。以下按性价比排序给出修改。

---

## 修改 1:重写 System Prompt(改 coach_commentary.py 的 _SYSTEM_PROMPT)

关键新增:
- 专业教练的「思考框架」(先分类→再解读工作段→交叉印证→给建议)
- 量化「评级标准」(让 LLM 知道 191ms 触地是精英级、VR 5.7% 是优秀)
- 允许更长、更有结构的输出

```python
_SYSTEM_PROMPT = """\
你是一位精英跑步教练,用数据驱动的方式分析训练,风格专业但口语化(伙伴型)。

【思考框架 — 必须按此顺序推理】
1. 定性:这是什么训练?(间歇/阈值/长距离/恢复)依据是工作段结构,不是全程均值。
2. 分段解读:必须分别解读工作段和恢复段。间歇跑的质量看工作段配速+组间心率回落,
   绝不能用全程平均配速评判。
3. 交叉印证:用多个指标互相验证一个结论。例如"心率漂移低 + 配速稳定 + 触地时间稳定
   → 后程没有失代偿"。单一指标不下结论。
4. 给方案:建议必须落到具体的下一次训练(配速区间、距离、强度)。

【量化评级标准 — 用这些锚点解读数据,不要含糊其辞】
- 触地时间 GCT: <200ms 精英 | 200-250ms 良好 | >250ms 待改善
- 垂直振幅比 VR: <6% 优秀 | 6-8% 良好 | >8% 偏高
- 心率漂移(cardiac drift): <5% 优秀 | 5-8% 正常 | >8% 后程失代偿
- HRR-60(1分钟心率回落): >30bpm 精英 | 20-30 良好 | <20 待观察
- 有氧解耦率: <5% 精英耐力 | 5-10% 达标 | >10% 后程效率衰减
- 步频: 170-185spm 是理想区间(配速越快步频越高)

【硬性约束 — 违反即失败】
1. 只能用提供的事实,不得虚构任何数字。没有的数据就说"本次未记录"。
2. 必须区分工作段与恢复段,禁止用全程均配速判断间歇质量。
3. 结论必须与规则层输出(training_type / fatigue_risk_level / recommendation)一致。
4. Level1 紧急信号(hrv_drop_pct≥20 或 rhr_spike_bpm≥7)必须最优先,放在建议第一条。
5. 不做医疗诊断,不用"加油/Fighting/💪"等空泛激励。
6. 有历史数据时,必须做纵向对比(如"触地从上次 205ms 降到今天 198ms")。

【输出格式】
返回 JSON,键为 summary / key_findings / strengths / watchouts / next_steps:
- summary: 2-4 句话,点明训练定性 + 最重要的1个发现
- key_findings: 数组,每项是"指标 + 数值 + 评级 + 含义"的完整解读(可以长)
- strengths / watchouts: 短句数组
- next_steps: 数组,每项是具体可执行的下一步(带配速/距离/强度)
全部简体中文。允许在 key_findings 里展开细节,不要为了简短牺牲专业度。
"""
```

---

## 修改 2:扩充 prompt_context 的数据颗粒度(改 _build_prompt_context)

现在只喂了聚合指标。要让 LLM 说出专业细节,必须喂逐公里/逐段序列。

需要在 fit_parser.py 的 ParsedFitActivity 里补充(如果还没有):
- per_km_splits: 每公里的 [配速, 心率, 功率, 触地, 步频]
- 逐段完整力学(不只是 pace/hr,还要 gct/vr/step_length)

然后在 _build_prompt_context 里加入:

```python
    # 逐公里分段(这是专业分析的基础)
    "per_km_splits": [
        {
            "km": i + 1,
            "pace_sec": split.pace_sec_per_km,
            "hr_bpm": split.avg_hr,
            "power_w": split.avg_power,
            "stance_ms": split.avg_stance_time,
            "cadence_spm": split.avg_cadence,
        }
        for i, split in enumerate(activity.per_km_splits)
    ],
    # 前后半程对比(揭示疲劳/负分段)
    "split_comparison": {
        "first_half": {...},
        "second_half": {...},
    },
    # 评级标准(让LLM有锚点)
    "rating_thresholds": {
        "stance_time_ms": {"elite": "<200", "good": "200-250"},
        "vertical_ratio_pct": {"excellent": "<6", "good": "6-8"},
        "hr_drift_pct": {"excellent": "<5", "normal": "5-8", "decoupled": ">8"},
    },
```

---

## 修改 3:加入历史对比(解决 Known gap #1)

这是让回复"像老教练"的关键。没有历史,再强的模型也只能就事论事。

最小可行方案(不需要完整数据库):
1. 每次分析后,把关键指标存到 api/data/history/{user}.jsonl
   (date, training_type, work_pace, gct, vr, hr_drift, ef_ratio)
2. 分析新活动时,读取同类型的最近 3-5 次,作为 history 字段喂给 LLM
3. LLM 就能说出"触地从 5/19 的 215ms 降到今天 198ms"这种趋势

```python
    "history": [
        {"date": "2026-06-18", "training_type": "threshold",
         "work_pace_sec": 235, "gct_ms": 199, "vr_pct": 5.8},
        # ... 最近同类型训练
    ],
```

---

## 修改 4:提高 temperature + 放宽 token

- temperature 0.3 → 0.5(0.3 太保守,回复会干巴巴)
- 确保 max_tokens 足够(专业分析需要空间,建议 2000+)

---

## 优先级建议

| 修改 | 工作量 | 效果 | 优先级 |
|------|-------|------|--------|
| 1. 重写 System Prompt | 10分钟 | ⭐⭐⭐⭐ | 立即做 |
| 2. 扩充数据颗粒度 | 半天 | ⭐⭐⭐⭐⭐ | 高 |
| 3. 历史对比 | 1-2天 | ⭐⭐⭐⭐⭐ | 高 |
| 4. 调参数 | 2分钟 | ⭐⭐ | 立即做 |

先做 1+4(15分钟,立即见效),再做 2,最后做 3。
