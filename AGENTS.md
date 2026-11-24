# ContextStroke — Agent Memory

跨机共享的项目记忆。改架构、算法规则、API 或已知坑时，**同步更新本文**；保持短、可扫读。

## 一句话

把 2D 笔触映射到预分割 PNG 图层组成的 **2.5D 场景**：判前后，枚举离散深度带候选（不做三维曲线重建）。

灵感：Skippy（on/off、深度候选）+ 分层平面展示。后续可能接 VLM。

算法说明（概念 + 例子，非 Agent 备忘）：`docs/algorithm.md`。

## 栈与端口

| | |
|---|---|
| 前端 | Vue 3 + TS + Vite + three.js → `5174`，`/api` 代理到后端 |
| 后端 | FastAPI + NumPy + Pillow → `8001` |
| 数据 | `backend/scenes/<id>/manifest.json` + PNG |
| 测 | `backend`: `pytest -q`；`frontend`: `npm run type-check` |

启动见根目录 `README.md`。改算法后需重启 uvicorn 才生效。

## 目录

```
backend/contextstroke/
  algorithm/
    solve.py          # 入口：resample → sample → spans → tracks
    resample.py       # 2D 重采样（保留拐点，间距约 ≤2px）
    sampling.py       # 命中采样、边界二分、背景前槽
    bands.py          # slots_for_hits（全序展开，现备用）/ slots_around_hits（单深度组前/后）
    spans.py          # fine_runs（参与关系选带）/ coarse_runs（最深命中包络）
    candidates.py     # 组合枚举、|Δ|≤1 过滤、fine∪coarse 去重、track 几何
    types.py          # Hit / Sample / Slot / Run
    scene/            # 清单、图层编辑、导入导出 zip
  server/api.py       # HTTP；算法不依赖 FastAPI
frontend/src/
  App.vue · api.ts · components/{Viewport,LayerPanel,CandidatePanel}
```

## 求解流水线

1. `resample_2d` → 采样点  
2. `sample_point` + `refine_boundaries` → on/off 与 hits（背景不算 on）  
3. `fine_runs` + `coarse_runs` → 两套 Run（各带可选 Slot）  
4. `build_tracks` → 合法组合、代价排序、summary 去重，最多约 32 条；默认选代价最低（同代价再比 `slot_sum`）

## 领域规则（当前算法）

1. **on / off**：非背景主体掩膜不透明 → on；只碰背景或空白 → off。  
2. **深度**：整数，**1 最前**；同深度共面。带如 `0-1`（主体前）、`1-2`（主体后）。  
3. **原子切段（fine 几何）**：连续 on 内命中集合变化则切开（地毯 → 拖鞋+地毯 → 地毯）。隔着 off 的两段不属于同一 contiguous chain。  
4. **按参与关系选带（核心，已落地）** — 约束落在「被谁切开」的段上，不是整条候选，也不是只留全序最前/最后两个端点。  
5. **连接过滤**：无 off 的相邻原子段 `|Δslot| ≤ 1`（`candidates.combo_valid`）；真实 off 可跨任意深度，只计代价。  
6. **候选合并**：fine 与 coarse 两路枚举后按 summary 去重；`selected` = 代价最低。  
7. **边界**：相邻 on/off 在掩膜轮廓二分贴边。

### Fine：参与者 → 最前一层的前/后

实现：`spans._participant_runs` → 每段 `slots_around_hits(最前参与者)`。

对连续 on 链里的每个原子段：

1. **本段命中**全部进入参与者集合。  
2. **端点切开**：看左右紧邻 on 段（`end+1 == start`，中间无 off）。邻段有、本段没有、且深度比本段自己的最前命中**更前**的主体，也加入参与者——它切开了这个端点。  
   - **不要求**两段命中集合相交。植物 → 植物+桌 → 桌：桌子段的端点仍算被植物切开。  
   - 隔着 off 的两段不算相邻，不互相引入参与者。  
3. 取参与者里**最浅深度组**，只用它的前带 / 后带（`slots_around_hits`）。更前的参与者优先：茶几一旦参与这段，这段就只剩茶几前/后，即使沙发或地毯也打在这段上。  
4. 茶几**没参与**的段（两端都不是茶几切口、命中里也没有茶几）不受茶几约束。

黄 / 蓝 / 橙（沙发最后、地毯中间、茶几最前；沙发与地毯不重叠；茶几上半叠沙发、下半叠地毯）：

| 段 | 谁切开 | 合法带 |
|----|--------|--------|
| 黄 | 只有沙发和地毯，两端都不是茶几切口 | 不受茶几前/后约束 |
| 蓝 | 茶几命中（茶几切开） | 只能茶几前 / 茶几后 |
| 橙 | 命中可能主要是沙发/地毯，但有一端是茶几边界 | 同样只能茶几前 / 茶几后 |

两层拖鞋叠地毯是同一条规则的特例：拖鞋碰到的段 + 以拖鞋切口为端点的地毯邻段 → 拖鞋前/后；拖鞋碰不到的纯地毯段若端点也不是拖鞋切口，则按地毯（或走 coarse）。

### Coarse：丢掉前层叠盖，按最深命中切

实现：`spans.coarse_runs`。

1. 每个 on 采样只保留**最深**命中（茶几叠在地毯上时丢掉茶几，只留地毯）。  
2. 最深命中的 id 集合变化则切开；每段 `slots_around_hits(该段最深命中)`。  
3. 效果：沙发与地毯不重叠时，粗读法按沙发段、地毯段各自的前/后走，**不会**再各出一套「整笔只按沙发」「整笔只按地毯」的全局叙事；茶几不参与这套时，下半段按地毯，不把茶几前/后套上去。  
4. 拖鞋始终叠在地毯上时，最深命中一直是地毯 → 整段 on 常合成一条地毯 coarse 读法（`2-3` / `3-4` 一类）。

### 与旧逻辑的差别（改动要点）

| 旧 | 现 |
|----|----|
| 连续链命中交集 I 非空 → **整链** fine 都绕嵌套最前主体 | 按**段**算参与者；茶几只约束它碰到的段和以它切口为端点的邻段 |
| coarse = 整段 on 的并集里**最后一层**一条 | coarse = 每采样最深命中再切段；多层后层可分段 |
| I 为空时 fine 用 `slots_for_hits` 展开多带 | fine 统一 `slots_around_hits(最前参与者)`；`slots_for_hits` 仍留在 `bands.py` 备用 |
| 植物切桌子时 coarse 恒定 `1-2` 常为 selected | 植物切开桌子邻段 → fine 可恒定 `0-1`，代价 0 时优先 selected |

### 期望候选速查

**拖鞋 depth=1 叠地毯 depth=3**（地毯 → 拖鞋+地毯 → 地毯…）：

| 叙事 | 合法带 |
|------|--------|
| fine（拖鞋参与的段） | `0-1`、`1-2` |
| coarse（最深=地毯） | `2-3`、`3-4` |

不应出现：细切段里混进地毯后，或粗读法给出拖鞋前（`3-4 → 0-1`、`0-1 → 2-3` 等）。

**植物 depth=1 穿越桌子 depth=2**：植物切开重叠/桌子邻段 → fine 可恒定植物前 `0-1`；coarse 仍可出桌子带 `1-2` / `2-3`。

## 已知问题 / 决策史

- **已否决**：  
  - 包络锁定（I 非空 → 整链强制同一 slot）→ 细切段失效。  
  - 只取全序最前与最后两个端点（中间层被丢掉）。  
  - 「茶几一参与 → 整条 on / 整套切分每一段都只能茶几前/后」。  
  - 每个主体各出一套全局叙事（沙发不重叠地毯时仍单独「只切沙发」「只切地毯」）。  
  - 对每个原子段直接 `slots_for_hits` 当切段依据（茶几会出现在不该约束的段上）。  
- **已落地**：参与关系选带（`spans._participant_runs`）+ 最深命中 coarse（`spans.coarse_runs`）；测试见 `test_front_subject_constrains_only_spans_it_participates_in`、拖鞋叠地毯、穿越层、`test_api` selected=`0-1`。  
- **仍开放**：连续 on 上是否再禁小步来回拧（单调）；Skippy 虚拟 off 桥；观察模式「切段依据」可视化应跟着**当前候选**的参与者上色，而不是原始最前命中掩膜。

## 前端交互备忘

- 图层面板「隐藏 / 显示」：仅前端 `LayerModel.visible`，不写清单；`applyScene` 保留本地可见性；视口与调整点选跳过隐藏层；**求解仍用全部图层掩膜**。

## Agent 约定

- 中文 UI / 用户可见文案；代码标识符英文。  
- 不擅自 commit / push；不改无关文件。  
- 动求解逻辑必补/改 `backend/tests/test_solve.py`（及必要时 `test_api.py`），跑通 pytest。  
- 场景清单已存在时，启动不会用内置色块覆盖用户编辑。  
- 本文是记忆源：改核心行为后更新「求解流水线」「领域规则」「已知问题」。
