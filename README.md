# ContextStroke

把二维笔触映射到预分割图层组成的 2.5D 场景里：判断笔触相对各主体的前后关系，并给出多种深度带候选。

灵感来自 Skippy 的 on/off / 深度候选思路，以及 AniGraphic 一类分层平面展示。当前阶段只做**离散深度位置判断**，不重建三维曲线；视觉语言模型（如 Qwen-VL）留作后续扩展。

## 功能概览

- **2.5D 视口**：透明 PNG 按整数深度叠放（1 为最前），绘制 / 调整 / 观察三种模式
- **图层管理**：添加、删除、合并本地 PNG；拖拽或「更近 / 更远」调整深度；同深度可共面
- **位置与缩放**：在「调整」模式拖动图层、滚轮缩放，或用左侧 X / Y / 缩放% 精确摆放，便于用分割图还原原场景
- **背景图层**：可把某一层设为背景（始终最远）。背景只负责画面底层显示；**只碰到背景的笔触算 off**，碰到主体才算 on
- **深度带候选**：每一段连续的 on 选择一条深度带（如 `0-1`、`1-2`、`4-5`），枚举前后与交替组合；相邻段深度差超过 1 则断开
- **边界贴合**：加密采样，并在掩膜轮廓上切换 on/off 颜色
- **导入 / 导出**：把当前场景（图层 PNG、位置缩放、深度顺序、背景标记）打成 zip 分享；他人可导入复用

## 目录结构

```
ContextStroke/
├── backend/                 # FastAPI + 求解算法
│   ├── contextstroke/
│   │   ├── algorithm/       # scene.py（场景/图层）· solve.py（笔触求解）
│   │   └── server/          # api.py
│   ├── scenes/              # 场景清单与 PNG（如 blocks）
│   ├── tests/
│   └── requirements.txt
└── frontend/                # Vue 3 + Vite + three.js
    └── src/
        ├── components/      # Viewport · LayerPanel · CandidatePanel
        ├── api.ts
        └── ...
```

## 环境要求

- Python 3.11+（开发时用过 3.14）
- Node.js `^22.18.0` 或 `>=24.12.0`
- 推荐端口：后端 `8001`，前端 `5174`（避免与本机其他实验项目冲突）

## 启动

### 1. 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn contextstroke.server.api:app --host 127.0.0.1 --port 8001
```

健康检查：`http://127.0.0.1:8001/api/health`

### 2. 前端

另开一个终端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开：`http://127.0.0.1:5174/`  
Vite 会把 `/api` 代理到 `8001`。

### 3. 测试（可选）

```powershell
cd backend
.\.venv\Scripts\python -m pytest -q
```

```powershell
cd frontend
npm run type-check
```

## 使用说明

| 模式 | 作用 |
|------|------|
| **绘制** | 在正视图拖动画笔。松笔后右侧给出深度带候选，默认选深度变化最小的一条 |
| **调整** | 拖动选中图层改位置，滚轮改缩放；左侧也可改数值。写回场景清单 |
| **观察** | 斜视查看遮挡；on 段落在对应深度带，更近平面可挡住笔触 |

**图层面板**

- 添加 / 删除 / 合并（勾选两个非背景图层）
- 「设为背景」：该层固定为最远，并参与画面显示，但不参与 on 判定
- 深度组之间拖拽：拖到一组上并入该深度，拖到间隙则单独成层

**候选含义**

- `0-1`：深度 1 之前（最前）
- `1-2`：深度 1 与 2 之间
- 最后一层为 `n` 时，其后为 `n-(n+1)`
- **空白（off）**：未碰到任何主体（可只碰到背景）；可跨层连接不同深度带的 on 段

## 求解规则（简要）

1. 保留手绘拐点，并加密到相邻采样约 ≤ 2 像素
2. 采样点命中非背景图层的不透明像素 → on；否则 → off
3. 相邻 on/off 在掩膜边界上二分，使颜色贴住轮廓
4. on 区域内若命中的主体集合变化（如地毯 → 拖鞋+地毯），会切成新的原子段；每段按自身命中选深度带
5. 候选是这些原子段的组合（含全前、中间带、交替等，上限约 32）
6. off 可跨任意深度差连接相邻段，只计入深度变化代价，不再断开
7. 绘制模式：整条笔触画在所有平面之前，颜色表示深度带；观察模式：按槽位 z 放置

## 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/scenes` | 场景列表 |
| `GET` | `/api/scenes/{id}` | 场景清单（含图层） |
| `GET` | `/api/scenes/{id}/files/{file}` | 图层 PNG |
| `POST` | `/api/scenes/{id}/layers` | 添加图层（JSON：`name`、`image_base64`、可选 `depth`） |
| `PATCH` | `/api/scenes/{id}/layers/{layer_id}` | 更新 `x` / `y` / `scale` / `background` |
| `DELETE` | `/api/scenes/{id}/layers/{layer_id}` | 删除图层 |
| `POST` | `/api/scenes/{id}/layers/merge` | 合并两个图层（`ids`、可选 `depth`） |
| `PUT` | `/api/scenes/{id}/depths` | 把前端深度顺序写回清单 |
| `POST` | `/api/scenes/{id}/export` | 导出 zip（可带当前 `depths`） |
| `POST` | `/api/scenes/import` | 导入 zip，创建新场景 |
| `POST` | `/api/solve` | 求解笔触（`scene`、`depths`、`stroke`） |

场景数据在 `backend/scenes/<scene_id>/`：`manifest.json` + PNG。清单一旦存在，启动时不会用内置色块场景覆盖你的编辑。

## 技术栈

- **前端**：Vue 3、TypeScript、Vite 8、three.js（`Line2` 画笔触）
- **后端**：FastAPI、NumPy、Pillow、Pydantic、pytest

## 现状与后续

已完成：分层展示、深度编辑、图层增删合并与变换、背景层、按 on 段的深度带候选、on/off 边界贴合。

计划中：用视觉模型辅助理解图层/深度；更完整的笔触三维形态（而不只是前后槽位）。
