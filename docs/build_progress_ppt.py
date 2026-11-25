"""Build a short related-work + progress PPT for ContextStroke."""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

OUT = Path(r"C:\Users\78324\Desktop\ContextStroke_相关工作与进度汇报.pptx")
ALT = Path(r"d:\Git_Project\ContextStroke\docs\ContextStroke_相关工作与进度汇报.pptx")

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

INK = RGBColor(0x1A, 0x1F, 0x2E)
MUTED = RGBColor(0x5A, 0x63, 0x75)
ACCENT = RGBColor(0x2F, 0x6F, 0xED)
SOFT = RGBColor(0xF4, 0xF6, 0xFA)


def set_run(run, size=18, bold=False, color=INK):
    run.font.name = "Microsoft YaHei"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def add_title_bar(slide, title, subtitle=None):
    box = slide.shapes.add_textbox(Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.7))
    tf = box.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = title
    set_run(run, 28, True, INK)
    if subtitle:
        sub = slide.shapes.add_textbox(Inches(0.6), Inches(0.95), Inches(12.1), Inches(0.4))
        stf = sub.text_frame
        stf.clear()
        sp = stf.paragraphs[0]
        sr = sp.add_run()
        sr.text = subtitle
        set_run(sr, 14, False, MUTED)


def add_bullets(slide, lines, left=0.6, top=1.5, width=12.1, height=5.5, size=18):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = box.text_frame
    tf.word_wrap = True
    tf.clear()
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.level = 0
        p.space_after = Pt(8)
        run = p.add_run()
        run.text = line
        set_run(run, size, False, INK)


def add_two_cols(slide, left_lines, right_lines, left_title, right_title):
    for x, title, lines in (
        (0.6, left_title, left_lines),
        (7.0, right_title, right_lines),
    ):
        t = slide.shapes.add_textbox(Inches(x), Inches(1.45), Inches(5.7), Inches(0.4))
        tf = t.text_frame
        tf.clear()
        p = tf.paragraphs[0]
        r = p.add_run()
        r.text = title
        set_run(r, 16, True, ACCENT)
        add_bullets(slide, lines, left=x, top=1.95, width=5.7, height=4.8, size=15)


# 1 cover
slide = prs.slides.add_slide(prs.slide_layouts[6])
box = slide.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.5), Inches(1.2))
tf = box.text_frame
tf.clear()
p = tf.paragraphs[0]
r = p.add_run()
r.text = "ContextStroke"
set_run(r, 40, True, INK)
p2 = tf.add_paragraph()
r2 = p2.add_run()
r2.text = "相关工作梳理 · 当前进度汇报"
set_run(r2, 26, False, ACCENT)
sub = slide.shapes.add_textbox(Inches(0.8), Inches(4.0), Inches(11.5), Inches(1.2))
stf = sub.text_frame
stf.clear()
sp = stf.paragraphs[0]
sr = sp.add_run()
sr.text = "把 2D 笔触映射到预分割图层组成的 2.5D 场景\n离散深度带候选 · 不做三维曲线重建"
set_run(sr, 16, False, MUTED)
foot = slide.shapes.add_textbox(Inches(0.8), Inches(6.6), Inches(11.5), Inches(0.4))
ftf = foot.text_frame
ftf.clear()
fp = ftf.paragraphs[0]
fr = fp.add_run()
fr.text = "简短汇报草稿 · 2026-11"
set_run(fr, 12, False, MUTED)

# 2 problem
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "问题与目标", "本项目在做什么")
add_bullets(
    slide,
    [
        "输入：预分割透明 PNG 图层栈（2.5D）+ 用户手绘 2D 笔触",
        "输出：笔触相对各主体的前后关系 → 若干离散深度带候选（如 0-1、1-2）",
        "不做：连续三维曲线重建 / 完整曲面建模",
        "动机：Skippy 的 on/off + 候选枚举思路，落到分层平面场景；后续可接 VLM",
        "现状定位：交互式几何推理原型 + 可演示系统（Vue + FastAPI）",
    ],
)

# 3 related overview
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "相关工作总览", "五篇论文如何落在「笔触 / 空间 / 视觉提示」坐标上")
add_bullets(
    slide,
    [
        "交互建模（几何）  Skippy — 单视图 3D 曲线；on/off 切段 + 候选轨迹",
        "视觉指令（机器人） RoVI — 手绘箭头/圆圈指挥机器人，补语言空间歧义",
        "视觉提示（MLLM） Draw-and-Understand — 点/框/自由形提示让模型懂「你指哪里」",
        "空间推理（VLM）  SpatialRGPT — 区域 grounding + 度量/相对空间问答",
        "图提示（空间关系） Graph-of-Mark — 在图上叠场景图，强化相对方位推理",
        "与 ContextStroke：Skippy ≈ 算法祖先；后四篇 ≈ 后续「图层语义 / 用户意图」接口",
    ],
    size=17,
)

# 4 Skippy
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "1. Skippy（最直接相关）", "Single View 3D Curve Interactive Modeling")
add_two_cols(
    slide,
    [
        "用户在已有 3D 几何前画 2D 笔触 → 推断 3D 曲线",
        "按 on/off（落在几何上/外）切分笔触，前后可复制成图",
        "枚举大量候选轨迹，用距离场 + 光滑性选优",
        "面向建模 / 相机路径等，输出连续 3D 曲线",
    ],
    [
        "继承：on/off 切段、候选枚举、交互式选择",
        "改写场景：预分割图层平面栈，而非三角网格",
        "改写目标：深度带槽位（0-1, 1-2…），非 3D 坐标曲线",
        "背景层仅显示；只碰背景算 off",
        "→ 本项目的「几何核心」直接对标 Skippy",
    ],
    "论文要点",
    "与 ContextStroke",
)

# 5 RoVI
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "2. Robotic Visual Instruction (RoVI)", "手绘视觉指令指挥机器人")
add_two_cols(
    slide,
    [
        "语言指挥机器人：空间不精确、冗长、场合受限",
        "RoVI：物体中心的手绘符号（箭头、圆、颜色、编号）",
        "把时空任务编码成可解释的 2D 草图",
        "VIEW 流水线：理解草图 → 生成操作动作",
    ],
    [
        "共同点：用「画」表达空间意图，补语言不足",
        "差异：RoVI → 机器人动作；我们 → 笔触深度语义",
        "可借鉴：箭头/编号等多符号视觉指令扩展交互",
        "远期：把深度带候选当作「可执行视觉指令」中间表示",
    ],
    "论文要点",
    "与 ContextStroke",
)

# 6 Draw-and-Understand
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "3. Draw-and-Understand", "视觉提示让 MLLM 理解「你想指什么」")
add_two_cols(
    slide,
    [
        "把 visual prompting 能力接入 MLLM",
        "支持点、框、自由形状等提示 + 语言",
        "MDVP 数据（约 120 万）与评测基准",
        "增强细粒度指称与交互理解",
    ],
    [
        "共同点：笔触/涂鸦是「指称」而非最终几何",
        "我们当前：掩膜命中做指称，尚未接大模型",
        "可对接：用户圈选/涂抹 → VLM 理解图层语义",
        "也可：把候选深度带解释成自然语言反馈",
    ],
    "论文要点",
    "与 ContextStroke",
)

# 7 SpatialRGPT
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "4. SpatialRGPT", "Grounded Spatial Reasoning in VLMs")
add_two_cols(
    slide,
    [
        "VLM 在 2D 任务强，度量/相对空间推理弱",
        "区域级 grounding + 空间问答（远近、宽高、距离）",
        "强调「指到区域」再谈空间关系",
        "含相对关系、度量估计、可通行性等",
    ],
    [
        "共同点：空间关系要「对着区域」说清",
        "我们：图层 = 显式区域；深度带 = 离散前后",
        "可对接：自动估计图层前后 / 校验深度编辑",
        "也可：用 VLM 解释「为什么选这条候选」",
    ],
    "论文要点",
    "与 ContextStroke",
)

# 8 GoM
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "5. Graph-of-Mark (GoM)", "图结构视觉提示增强空间推理")
add_two_cols(
    slide,
    [
        "Set-of-Mark：物体标号，但对象彼此孤立",
        "GoM：把场景图叠到像素上（关系边）",
        "提升相对方位 / 定位等 zero-shot 表现（最高约 +11pp）",
        "训练免费的 prompting 路线",
    ],
    [
        "共同点：显式编码物体间空间关系",
        "我们的图层深度序 ≈ 简化版有序图",
        "可借鉴：把深度组 / 遮挡边画成 mark 喂给 MLLM",
        "候选轨迹也可看成「沿深度图的一条路径」",
    ],
    "论文要点",
    "与 ContextStroke",
)

# 9 comparison table slide
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "对照小结", "输入 · 输出 · 对我们的价值")
rows = [
    ("工作", "核心输入", "核心输出", "对我们"),
    ("Skippy", "2D 笔触 + 3D 网格", "3D 曲线候选", "算法范式直接来源"),
    ("RoVI", "箭头/圆等草图", "机器人动作", "视觉指令交互灵感"),
    ("Draw-and-Understand", "点/框/自由形 + 图", "指称理解", "后续 VLM 指称接口"),
    ("SpatialRGPT", "区域 + 空间问句", "空间答案", "深度/前后语义校验"),
    ("Graph-of-Mark", "带关系的 mark 图", "更强空间推理", "图层关系提示格式"),
    ("ContextStroke", "笔触 + PNG 图层", "深度带候选", "—"),
]
table = slide.shapes.add_table(len(rows), 4, Inches(0.5), Inches(1.5), Inches(12.3), Inches(5.2)).table
table.columns[0].width = Inches(2.6)
table.columns[1].width = Inches(3.4)
table.columns[2].width = Inches(3.2)
table.columns[3].width = Inches(3.1)
for i, row in enumerate(rows):
    for j, cell_text in enumerate(row):
        cell = table.cell(i, j)
        cell.text = cell_text
        for p in cell.text_frame.paragraphs:
            for run in p.runs:
                set_run(run, 12 if i else 13, i == 0, INK if i else ACCENT)

# 10 progress
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "当前进度：已完成", "可运行原型（前端 5174 / 后端 8001）")
add_bullets(
    slide,
    [
        "2.5D 视口：绘制 / 调整 / 观察三种模式；斜视看遮挡",
        "图层：增删合并、深度拖拽、X/Y/缩放、背景层（显示但不计 on）",
        "求解：重采样 → 掩膜命中 → 从深到浅按主体切割 → 深度带候选（≤32）",
        "规则：hit-set 原子段、镂空孔段、更深轮廓认领、真 off 跨层桥、|Δ|≤1 连接",
        "工程：场景 zip 导入导出；算法模块拆分（solve / scene 包）；pytest 覆盖",
    ],
    size=17,
)

# 11 pipeline
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "算法流水线（当前）", "离散深度位置判断，不是曲线重建")
add_bullets(
    slide,
    [
        "1. resample_2d：保留拐点，间距约 ≤2px",
        "2. sample + refine：on/off（背景不算 on），边界二分贴轮廓",
        "3. depth_passes：深度从深到浅，每层一次切割；段只能在该主体前或后",
        "4. build_tracks：各次切割分开枚举 → |Δ|≤1 / off 桥过滤 → summary 去重排序",
        "例子：架子 8 + 沙发 7 → 不会错误拼出 7-8→6-7；绿框镂空孔留在绿色那一次",
    ],
    size=17,
)

# 12 next
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "下一步与开放问题", "从「几何原型」走向「语义 + 交互」")
add_two_cols(
    slide,
    [
        "切段依据可视化（调试/论文图）",
        "更多真实分割场景验证",
        "候选解释：为何选这条 summary",
        "笔触三维形态（不止槽位）— 可选",
    ],
    [
        "接 VLM：图层命名 / 自动前后建议（SpatialRGPT 方向）",
        "视觉提示：用户涂抹指称图层（Draw-and-Understand）",
        "关系 mark：深度图喂给模型（GoM）",
        "指令扩展：箭头式任务笔触（RoVI）",
    ],
    "近期工程",
    "中期研究接口",
)

# 13 takeaway
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_title_bar(slide, "一句话总结")
add_bullets(
    slide,
    [
        "ContextStroke = Skippy 的候选枚举思想 × 2.5D 图层场景",
        "当前交付：可交互系统 + 明确的离散深度带求解规则",
        "相关 VLM/视觉提示工作：不是替代几何求解，而是下一阶段的语义接口",
        "汇报焦点建议：演示一条穿越多层的笔触 → 看候选如何变化",
    ],
    size=20,
)

for path in (OUT, ALT):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(path)
        print("saved", path)
    except Exception as exc:
        print("failed", path, exc)
