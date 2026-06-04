## 一、概览与研究框架

### 1.1 研究范围与时间窗口

本报告聚焦 2023–2026 年间全球具身智能（Embodied AI）的技术与产业演进，重点关注：

- 技术路线与系统架构：模型、算法、本体与系统栈[1][2][3][4][5]  
- 代表性公司与平台：人形/移动/软体机器人及 “Physical AI” 软件栈[6][7][8][9][10][11]  
- 产品形态与商业化进度：仓储、制造、服务、医疗等场景[7][8][12][13][14][15]  
- 融资与资本动向：大额融资、估值与营收概况[5][16][17][18][19][11]  
- 核心团队与组织特征：技术、硬件、商业团队结构与演化[20][21][22][23][24][25]  
- 区域政策与标准环境：尤其中国在具身智能标准与政策上的布局[26][27][4]  

**局限说明**：  
1）多数公司未披露详细模型参数、算法实现或完整组织结构；本报告在公司层面仅能给出“技术方向–架构模式–大致团队画像”，难以给出现阶段可比的量化技术指标与精确团队比例[28][6][20][21][29][23]。  
2）融资与估值信息高度不对称，很多关键轮次与金额仅见于单一新闻或数据库摘要，报告中凡涉及融资金额/估值的内容，均在可行范围内注明来源和不确定性[5][16][18][19][30][11]。  

### 1.2 具身智能技术栈：从感知到行动

学术综述普遍将具身智能系统拆解为多层：感知、身体/执行器、控制与决策、学习机制与环境交互，构成从感知到行动的完整闭环[1][2][3]。典型 “Embodied AI Stack” 可抽象为四层[13][14]：

- **感知层**：视觉、力觉、位置等多模态传感与特征编码；  
- **模型层**：大模型与世界模型，用于感知–任务理解–预测（含 VLA 模型、世界模型、强化学习等）[2][3][31][32][33][34][12]；  
- **控制层**：运动规划与控制（端到端神经控制 + 模块化安全控制并存）[2][35][13]；  
- **应用层**：仓储、制造、服务、医疗、移动等具体任务流程[7][8][13][14][15]。  

中国信通院与 IDC 的产业研究进一步提出“**模型驱动、软件定义、硬件重构**”的具身智能技术栈：以具身基础模型为系统“操作系统”，任务逻辑与控制策略通过软件配置，而机器人本体与执行器按模型与场景需求快速迭代[4][5][36]。

### 1.3 主流技术路线总览

综合多篇综述与产业报告，可将 2023–2026 年具身智能的主流技术路线概括为四条互相交织的主线[1][2][3][31][32][33][37][38][7][12][35][13][14]：

1. **端到端深度强化/模仿学习路线**：通过强化学习或人类/遥操作示教学习策略，实现从感知到动作的端到端控制[1][2][37][7][12]。  
2. **模块化感知–规划–控制路线**：保持传统机器人“感知–规划–控制”结构，但以深度学习替换部分子模块，并通过统一软件栈调度[1][2][3][39][40][13][14]。  
3. **LLM / VLA / 具身大模型路线**：以大语言模型、视觉–语言–行动（VLA）模型或具身基础模型为中枢，负责任务理解、规划与多模态融合，控制底层执行[2][3][31][32][37][38][12][35]。  
4. **世界模型 + 虚实融合训练路线**：构建显式世界模型进行环境动力学建模与“想象”，结合仿真生成海量交互数据，通过 sim2real 迁移到真实机器人[3][31][32][33][34][41][4][29]。  

下文将以这一框架为主线，将代表性公司映射到各路线，并梳理其产品进度、商业化情况和团队结构。

---

## 二、技术路线与系统架构梳理

### 2.1 具身智能的分层与机器人形态

**系统分层**  
综述指出，具身智能涉及：感知（visual/tactile）、身体与执行器、控制与决策、学习机制（强化学习、模仿学习、自监督等）、环境交互五个模块[1][2][3]。工程实现通常采用分层架构，将传感、模型、控制与应用解耦[13][14]。

**机器人形态**  
具身智能的“身体”不局限于人形，包括：  
- 通用人形与移动平台；  
- 专用工业/服务机器人（机械臂+末端执行器、AGV/AMR 等）；  
- 软体机器人（柔性关节与智能材料）；  
- 群体机器人（多体协作）[1][3][42][43]。  

软体机器人研究指出，其柔性结构和材料本身承担部分形变与适应，实现“**在材料层面实现部分智能**”，在复杂环境如水下、狭窄空间中具有优势[42][43][20][16]。

### 2.2 LLM / 多模态基础模型驱动的路线

#### 2.2.1 LLM 作为任务规划与语言–行动接口

面向具身 AI 的特邀综述将近年工作划分为“具身 AI with LLM/MLLM”与“具身 AI with World Models”两大方向[2][31][32]：

- LLM/MLLM 用于任务分解、指令解析、工具调用与高层决策；  
- 通过 API 调度传统控制模块或低层策略控制机器人执行任务[2][31][32][37][38]。  

Nature Machine Intelligence 的 ELLMER 框架是典型案例：将 GPT‑4 与检索增强生成（RAG）集成，使机器人在真实环境中理解复杂任务、分步骤规划并调用底层工具，完成整理房间、使用工具等多步任务[37][38]。

在移动服务机器人领域，Robotics 综述总结了“现有移动平台 + LLM/VLM”的方案：通过 GPT‑3/4 等基础模型解析自然语言指令，结合视觉基础模型进行场景理解，实现家庭、酒店、医疗等服务任务[7][8][44]。典型系统结构为“移动平台 + LLM/VLM 模块 + 传统定位与导航”。

#### 2.2.2 Vision–Language–Action（VLA）与具身大模型

VLA 综述将面向具身 AI 的 VLA 模型统一为“视觉编码器 + 语言编码器 + 动作/控制输出模块”的架构，可通过模仿学习、强化学习或离线数据训练等方式，用于室内服务、操作与导航[12][39][35]。这一架构被 Google DeepMind、NVIDIA、Meta 等机构采用，并逐步扩散到产业[12][35]。

产业侧，具身大模型路线的代表包括：

- **Figure AI – Helix VLA**  
  Helix 是 Figure 的视觉–语言–行动大模型，采用 System 1/2 双系统架构：System 1（约 200Hz）负责底层运动控制与反射反应，System 2 负责高层规划与决策；Helix 统一建模视觉、语言和行动，实现从感知到动作的闭环控制，并支持设备端学习[28][45][10][46]。  
  这一路线属于“具身 VLA 大模型 + 通用人形本体 + 端到端闭环”的典型范式。

- **智元 – ERA‑42 具身大模型**  
  智元自研 ERA‑42 端到端 VLA 大模型并结合世界模型，用于驱动全尺寸人形机器人，形成“具身大模型 + 通用人形平台”的一体化产品[29][47]。  
  其提出“一体三智”架构，在统一体系下融合交互智能、作业智能和运动智能，以具身大模型为核心[48][49]。

- **Physical Intelligence – 通用具身基础模型**  
  Physical Intelligence（π）定位为“将通用 AI 带入物理世界”，目标是开发能够控制任意机器人完成任意任务的基础模型，并通过 cross‑embodiment 学习使模型适配多种机器人形态[18][50][51][19]。  
  团队成员来自 Google Research、DeepMind、UC Berkeley 等机构，获得 CapitalG 等投资[19][30][23][52]。

中国信通院、IDC 和多家机构报告认为，具身基础模型/具身大模型正在成为机器人的“操作系统”[4][5][36]，上述公司是这一趋势的主要实践者。

### 2.3 世界模型与虚实融合训练

世界模型综述将世界模型定义为：支持智能体在复杂环境中执行感知–预测–规划–行动的核心结构，包括视频预测、状态空间、3D 场景等多种形式，以及自监督世界模型与 Dreamer 类生成模型等[31][32][33][34][41]。其在机械臂操作、移动导航、人形运动规划中可通过内部“想象”环境变化来进行基于模型的决策[33][34][41]。

与 LLM 的结合方式之一是：世界模型负责环境动力学与可视化“想象”，LLM 负责语义理解与任务分解，两者构成具身多模态中枢[31][32][33][34]。训练层面广泛采用虚实融合：

- 在仿真中生成大量交互数据；  
- 通过 sim2real 迁移与现实数据微调下降低真实采集成本[34][41][4][29]。  

智元在产业中给出一个世界模型 + 虚实融合路线的实践样本：通过 ERA‑42（VLA + 世界模型）并依托关联公司觅蜂科技构建覆盖真实与仿真多维数据的训练体系，实现从仿真到现实迁移[29][47]。

### 2.4 模块化感知–规划–控制与“软件定义机器人”

尽管端到端路线快速发展，大量工业与物流部署仍采用模块化感知–规划–控制体系[1][2][3][39][40][13][14]。以代表公司为例：

- **Mujin – MujinOS**  
  MujinOS 是无代码部署码垛、拣选和车队自动化的统一软件平台，将感知、规划与控制集成，使用户通过高层任务描述自动生成机器人程序，适配复杂物流与制造环境[40][53]。  
  技术路径：**感知/路径规划/控制模块化 + AI 优化 + 无代码平台**。

- **Covariant – 仓储/制造 AI 软件栈**  
  Covariant 提供 AI 驱动的机器人拣选与操作软件栈，以深度学习视觉 + 运动规划为核心，通过 AI-first 软件层适配异构机械臂[9][26][54][55][56]。  
  创始团队包括 Peter Chen 和 Pieter Abbeel 等深度强化学习研究者[9][26][55][56]。

- **Intrinsic – Software-defined Robotics**  
  Intrinsic 面向机器人集成商，提供 AI 驱动软件平台，通过学习、仿真与自动规划简化工业机器人部署，与 KUKA 等合作[26][54][11][57][58]。  
  2025 年以 247 人团队实现约 2720 万美元经常性收入[59][60]，体现其商业化能力。  

优必选技术栈则体现“本体–控制–多模态感知–云/边协同”的三层架构：底层伺服驱动、电机与关节控制，中层运动控制与姿态平衡，上层视觉与语音多模态感知及云/本地 AI 模型的任务决策[61][62]。

### 2.5 端到端强化/模仿学习与遥操作示教

端到端深度强化学习与模仿学习仍是具身智能的重要路线[1][2][7][12]。产业中普遍采用“人类/遥操作示教 + 数据驱动 + 学习控制”的范式[8][44]：

- **1X Technologies – NEO**  
  NEO 人形机器人通过人类远程遥操作示教，将示教数据用于训练机器人执行任务，是典型“人类示教 + 数据驱动 + 深度学习策略学习”路线[8][44][63]。

- **Sanctuary AI – Carbon**  
  Carbon 系统结合通用机器人平台与 AI 控制系统，利用遥操作数据和学习型控制缩短任务训练时间，据称可将任务训练时间减少约 88%[8][44][24][64]。

在 VLA 模型与移动服务机器人中，模仿学习与离线数据训练也非常普遍[12][39][35]。

### 2.6 边缘部署与工程约束

具身基础模型在边缘硬件上的部署受模型规模、边缘算力、延迟、能耗与成本等约束，需要模型架构、训练策略与嵌入式硬件协同设计，并采用专用硬件与模型压缩技术[35][65]。  
SAE 世界大会白皮书在物流、制造、医疗与移动机器人部署中强调，将具身智能模块集成到传统控制系统时，安全、信任与人机协作是关键挑战[27][36]。

---

## 三、按技术路线划分的代表性公司与技术路径

本节在上述路线框架下，按“具身大模型 + 通用人形”“人形本体 + 产业场景”“Physical AI 软件栈”“遥操作 + 学习控制”“康复 + 人形”的维度梳理代表公司。

### 3.1 具身大模型 + 通用人形本体

#### 3.1.1 Figure AI（美国）

- **技术路径**  
  - Helix VLA 大模型 + System 1/2 双系统架构：System 1（约 200Hz）负责底层运动与反射控制，System 2 负责高层规划[28][45]。  
  - 统一视觉、语言与行动，实现从感知到动作的闭环控制，并支持设备端学习[28][45][10][46]。  
  - 主张通过真实世界数据进行端到端学习，是“具身 VLA 大模型 + 通用人形本体”的代表[28][45][10][46]。  

- **产品进度**  
  - 2024–2026 年，Figure 02 在仓储等场景进行长时间连续分拣测试，据报道可连续运行 24 小时以上，验证工程可靠性[15][66]。  
  - 实际商用部署规模与收入数据在现有证据中尚未披露。

- **团队与组织**  
  - 2024 年 6 月公司约有 140 名员工，其中约 60% 为工程岗位，许多工程师拥有 MIT 等高校博士学位[50][51]。  
  - LinkedIn 显示 2025 年公司规模为 201–500 人[10]，表明 2024–2025 年员工快速扩张。  
  - 创始人 Brett Adcock 曾创立 Vettery（约 1 亿美元卖给 Adecco）和 Archer Aviation（以约 27 亿美元估值在纽交所上市），具备连续创业与资本运作经验[46][30]。  

- **融资与估值（证据有限）**  
  - Wikipedia 记载 Figure AI 在 2025 年末估值约 390 亿美元[30]，但现有证据未见具体轮次与金额，需谨慎使用。

#### 3.1.2 Tesla Optimus（美国）

- **技术路径**  
  - Optimus 归属于 Tesla AI & Robotics 统一团队，与自动驾驶共享 AI 技术栈[31][32][67][68][69]。  
  - 采用多摄像头视觉网络、端到端神经网络，从感知到动作统一建模；通过大规模车队数据训练，强调端到端与数据驱动代替模块化规则系统[31][32][67][68][69]。  
  - 是“统一车辆与人形 AI 栈 + 通用人形本体”的路线代表。  

- **产品与进度**  
  - Optimus 已在 Tesla 工厂内部执行简单物流与搬运任务，用作验证平台[32][67]，尚未公开大规模外部商用数据。  

- **团队结构**  
  - 具体 Optimus 团队的员工人数与职能分布未公开；仅知其纳入 Tesla AI & Robotics 统一团队[31][67]。

#### 3.1.3 智元机器人（中国）

- **技术路径**  
  - 采用“一脑多形”架构，以具身智能“脑”驱动多种机器人形态[70][71]。  
  - 自研 ERA‑42 端到端 VLA 大模型并结合世界模型，用于驱动全尺寸人形机器人[29][47]。  
  - 提出“一体三智”架构，在统一体系下融合交互智能、作业智能与运动智能，以具身大模型为核心[48][49]。  
  - 行业分析将智元归类为“具身智能基础大模型 + 通用本体平台”的典型公司[72][73]。  

- **产品进度**  
  - 2023 年 8 月发布首款具身智能机器人“远征 A1”，2024 年 12 月开始通用具身机器人商业化/批量生产[74][73]。  
  - 2026 年 3 月，远征 A3 第 10,000 台下线[71][74]。  
  - 行业媒体称，2025 年智元与宇树合计占全球人形机器人市场约 71% 份额（该数字来源于媒体报道，统计口径与样本未公开，需谨慎解读）[73]。  

- **团队与组织**  
  - 公开报道强调创始团队来自头部互联网公司与高校，组织强调软硬一体与多场景协同[73][48][49]。  
  - 具体员工人数与职能比例未公开，团队结构部分仍为信息缺口。

### 3.2 通用/类通用人形 + 仓储/制造自动化

#### 3.2.1 Agility Robotics（美国）

- **技术路径与产品**  
  - 代表产品 Digit 是双足人形机器人，面向仓储与物流自动化场景[15][66]。  
  - 通过摄像头、激光等多模态感知系统与运动控制算法，在仓库中执行包裹搬运等任务，实现人机协同[15][66]。  
  - 技术路径可归类为“人形本体 + 感知/控制算法 + 工厂/仓储场景”，是否集成大模型/世界模型尚无公开细节。  

- **产品与商业进度**  
  - Digit 部分部署于 Amazon、GXO 等企业的仓储系统中，用于试点或早期商用[15][66]。  
  - 具体订单量与收入数据尚未公开。  

- **团队与组织**  
  - RoboFab 工厂用于 Digit 大规模生产，公司从研发型创业公司向具备生产与供应链能力的企业过渡[75][76]。  
  - 员工数从 2024 年的 284 人增长至 2025 年的 436 人[23][52]；LinkedIn 显示规模为 201–500 人[75]。  
  - 引入来自 Amazon、Tesla 等大型科技公司的高管强化制造、供应链与商业化职能[76][77][78]。

#### 3.2.2 Unitree 宇树科技（中国）

- **技术路径与产品**  
  - 以高性能人形与四足机器人本体及核心零部件见长，招股书称其为“世界知名、国际领先的高性能通用机器人公司”[20][16][21]。  
  - 主要路线为“本体 + 关键部件 + 具身智能模型”，但公开资料更聚焦本体与部件，模型层细节披露有限[20][16][21][72]。  

- **产品与商业进度**  
  - 参与全球人形机器人公司前 15 榜单，与 Tesla、Figure 等公司同列[79][80]。  
  - 具体人形机器人产品的部署数据有限，更多数据来自四足机器人在安防、教学等垂直场景的应用[43][20]。  

- **融资与资本**  
  - B2 轮融资近 10 亿元人民币[16]。  

- **团队结构**  
  - 截至 2025 年 9 月末，公司约 175 名研发人员，占总员工 36.46%，总员工约 480 人[22][61]。  
  - 招股书提供了按研发、生产、销售、管理等职能的员工人数与比例，是其团队结构的权威来源[20][22]。  
  - 招聘页面显示 AI 算法、机器人控制、嵌入式开发和硬件设计等岗位远多于商务岗位[42][43]。

#### 3.2.3 优必选 UBTECH（中国）

- **技术路径与产品**  
  - 自称“领先的人形机器人和智能服务机器人公司”，有教育、服务与人形多条产品线[61][62][81]。  
  - 技术栈分层：底层伺服驱动器、电机与关节控制；中层运动控制与姿态平衡；上层视觉与语音多模态感知与云/本地 AI 模型[61][62]。  
  - 通过将 AI 嵌入服务与人形机器人实现更智能的人机交互与自主行为[61][62]。  

- **产品与商业进度**  
  - 2023 年 12 月在港交所上市后，2025–2026 年报告披露了营收、毛利率与订单情况，表明其在教育与服务机器人领域具备较成熟收入结构[21][22][81]。  
  - 部分报道提及其人形机器人 Walker 在吉利、羽田机场等场景试点[61][62]。  

- **团队与组织**  
  - 上市公司报告提供按研发、生产、销售、管理分类的员工人数与比例[21][22][81]。  
  - 显示公司已形成完整的研发–制造–销售–管理链条，是典型“成熟工程组织 + 上市公司治理结构”的具身智能企业。

#### 3.2.4 Apptronik（美国）

- **技术路径与产品**  
  - 起源于德州大学奥斯汀的 Human Centered Robotics Lab，专注人形机器人及相关技术[24][64][82]。  
  - 现有证据未披露其具身智能模型细节，仅可确认其作为人形本体公司，在技术与产业界具有一定影响力[24][64]。  

- **团队与组织**  
  - 2026 年 4 月新闻稿称公司拥有约 350 名员工[24][64][82]。  
  - 管理团队包括联合创始人兼 CEO Jeff Cardenas、联合创始人兼 CTO Dr. Nick Paine 等[82][25]。  
  - 早期 LinkedIn 数据显示员工规模为 51–200 人[77][78]，表明 2025–2026 年快速扩张。

### 3.3 Physical AI 软件栈 + 工业/仓储机器人

#### 3.3.1 Mujin（日本）

- **技术路径与产品**  
  - MujinOS 提供无代码部署码垛、拣选和机器人车队自动化的软件平台，将感知、规划与控制集成，支持复杂物流与制造环境的自动化[40][53]。  
  - 是典型“Physical AI 软件栈 + 通用机械臂/机器人”的路线。  

- **产品进度与商业化**  
  - 在日本与北美、欧洲多地实现实际部署，提升物流与制造效率[40][53][83][84]。  

- **团队与组织**  
  - 公司总部位于东京，创始人为 Ross Diankov 和 Issei Takino（Tracxn 报道提及 Kazuyuki Takino）[53][83]。  
  - 在荷兰设立欧洲办公室，并任命区域领导，展示出全球化组织结构[83][84][63]。  

#### 3.3.2 Covariant（美国）

- **技术路径与产品**  
  - Covariant 提供 AI 驱动的机器人拣选与操作软件栈，使用深度学习视觉 + 运动规划，并通过 AI-first 软件层适配异构机械臂系统[9][26][54][55][56]。  

- **团队与背景**  
  - 创始团队包括 CEO Peter Chen 和首席研究科学家 Pieter Abbeel 等，来自伯克利等顶级学术机构[9][26][55][56]。  
  - 技术路线强烈受深度强化学习与机器人学习研究传统影响。  

#### 3.3.3 Intrinsic（美国/欧洲）

- **技术路径与产品**  
  - Alphabet 旗下的 AI 机器人软件公司，面向集成商提供软件平台，通过学习、仿真与自动规划简化机器人应用开发[26][54][11][57][58]。  
  - 与 KUKA 等工业机器人厂商合作推动“软件定义机器人”[26][54][11][57]。  

- **商业与规模**  
  - GetLatka 数据显示，Intrinsic 2025 年以 247 名员工实现 2720 万美元经常性收入，估值约 8150 万美元[11][59][60]。  

- **团队与组织**  
  - CEO Wendy Tan White 曾创立 Moonfruit，并有 Alphabet 体系内经验[57][58]。  
  - 团队在企业软件商业化与机器人技术两方面具备优势。

### 3.4 遥操作示教 + 学习控制

#### 3.4.1 1X Technologies（挪威–美国）

- **技术路径与产品**  
  - NEO 人形机器人通过人类远程遥操作示教获得任务执行数据，使用深度学习策略进行学习，是“遥操作示教 + 学习控制”路线[8][44][63]。  

- **团队与组织**  
  - CEO Bernt Bornich，VP of Product & Design Dar Sleeper（曾在 Tesla 担任产品负责人）[82][25][63]。  
  - 员工规模与融资信息在现有证据中仅零散出现，缺乏完整数据。

#### 3.4.2 Sanctuary AI（加拿大）

- **技术路径与产品**  
  - Carbon 系统结合通用机器人本体与 AI 控制，通过遥操作数据与学习型控制将任务训练时间减少约 88%[8][44][24][64]。  

- **团队与组织演化**  
  - 公司公告显示，联合创始人 Geordie Rose 在 2024 年前后卸任 CEO，James Wells 担任 CEO[24][82][25]。  
  - 2026 年 3 月公司有约 163 名员工，分布在六大洲[75][76][77]。  
  - 官方博客指出，公司从研发中心向部署与商业化阶段转型，领导团队相应调整[77][78]。

### 3.5 康复 + 通用人形双轮驱动：傅利叶智能（中国）

- **技术路径与产品**  
  - 傅利叶最初聚焦康复机器人，在医疗与康复场景形成产品与数据积累[85][86]。  
  - 之后推出 GRx 系列人形机器人，构建通用机器人平台 + AI 算法的具身智能系统[85][86][70][71]。  

- **团队与组织**  
  - 招聘页面显示大量工程与研发岗位，强调工程师文化[70][71]。  
  - 组织结构呈现“康复业务 + 通用人形业务”的双业务线协同。

---

## 四、产品形态与商业化进度

### 4.1 人形机器人：从 Demo 到量产

- **规模量产能力**  
  - 智元：2024 年 12 月开启远征系列批量生产，2026 年 3 月远征 A3 第 10,000 台下线[71][74]。  
  - EngineAI：深圳 T800 人形机器人生产线每约 15 分钟下线一台，形成接近 1 万台级交付能力[5][36][13][14]。  
  - Agility：RoboFab 工厂支持 Digit 的大规模生产[75][76]。  
  - Unitree：兼具人形与四足本体及核心部件产线，在全球人形公司榜单中位列前 15[20][16][21][79][80]。  

- **应用场景与客户**  
  - 仓储/物流：Digit、Optimus、Unitree、EngineAI T800 等重在仓储与工厂物料搬运等场景[8][15][66][79][80]。  
  - 制造/汽车：优必选 Walker 与部分国外人形在汽车生产线试点[61][62]。  
  - 服务/康复：傅利叶在康复场景形成稳定业务，再向通用人形拓展[85][86]。  

- **商业成熟度差异**  
  - 优必选等上市公司提供相对完善营收与利润数据[21][22][81]；  
  - Unitree 等通过招股书披露部分收入与团队信息[20][22]；  
  - Figure、Physical Intelligence 等更多停留在估值与融资新闻阶段，收入与部署数据较少[18][19][30][52]。

### 4.2 Physical AI 软件在工业/仓储的部署

- Mujin、Covariant、Intrinsic 在工厂与仓储中提供 AI 软件栈，为传统机械臂和移动机器人提供统一感知–规划–控制平台[40][53][9][26][54][11]。  
- 相比自研人形本体，软件栈路线更容易通过 SaaS 或项目模式变现，并与现有工业基础设施兼容[12][39][13][14]。

### 4.3 移动服务与软体/专用机器人

- 移动服务机器人：基于 LLM/VLM 的移动服务机器人通过自然语言交互与视觉理解执行家庭、酒店、医疗任务[7][8][44]。  
- 软体机器人：在复杂环境（如水下、狭窄空间）中通过柔性结构和智能材料实现具身智能[42][43][20][16]。

### 4.4 安全与系统集成

SAE 世界大会白皮书指出，在物流、制造、医疗等领域部署具身智能时，安全、信任与人机协作为重点议题，需要配套的安全标准与工程实践[27][36]。这对人形与 Physical AI 软件的规模化商用构成约束。

---

## 五、融资格局与资本动向（信息有限）

### 5.1 已披露的重点融资案例

在现有证据中，能相对清晰识别的融资与资本事件包括：

- **EngineAI**：完成 pre‑A++ 与 A1 轮融资，总金额接近 10 亿元人民币，专注具身智能人形机器人[5][36][13][14]。  
- **Unitree**：B2 轮融资近 10 亿元人民币，由 90 后创业者创立[16]。  
- **Physical Intelligence**：获得 CapitalG 等机构支持，PitchBook 显示其拥有约 80 名员工[18][19][30][23][52][59][60]。融资具体轮次与金额未公开。  
- **Intrinsic**：2025 年经常性收入约 2720 万美元，估值约 8150 万美元，反映出资本市场对 AI 机器人软件栈的认可[11][59][60]。  
- **Figure AI**：Wikipedia 提到 2025 年末估值约 390 亿美元[30]，但具体融资轮次与金额缺失。  

由于缺乏系统的融资数据库或官方披露，本报告无法建立完整的“公司–轮次–金额–投资机构”表，仅能从上述案例中观察趋势。

### 5.2 资本偏好与技术路线

在现有有限信息下，可见以下倾向：

- **具身基础模型与平台公司**（Figure、Physical Intelligence、Intrinsic、Covariant 等）更易获得高估值或大额融资[9][26][18][19][30][11][59][60]；  
- **具备规模化产线与本体能力的企业**（智元、Unitree、EngineAI）在中国市场获得数亿元级融资与政策支持[5][36][20][16][71][74][72]；  
- 工业与物流软件公司（Mujin、Intrinsic、Covariant）通过可见的经常性收入与项目订单，向资本展示较清晰的商业模式[40][53][9][26][54][11][59][60]。

---

## 六、核心团队与组织特征

### 6.1 本体与人形企业的团队结构

- **Unitree**  
  - 约 175 名研发人员，占总员工 36.46%，总员工约 480 人[22][61]。  
  - 招股书与招聘信息表明，以研发与制造为主，商务与运营团队占比较小[42][43][20][22]。  

- **优必选 UBTECH**  
  - 上市公司报告披露按研发、生产、销售、管理分类的员工人数与比例[21][22][81]。  
  - 显示其在研发与生产之外拥有明显规模的销售与管理团队，组织结构更接近成熟消费/工业科技公司[21][22]。  

- **Agility Robotics**  
  - 员工从 284 增至 436（2024–2025 年），管理层引入来自 Amazon、Tesla 等公司的高管[23][52][76][77][78]。  
  - 组织从工程主导向制造、供应链与商业化并重转型。  

- **Apptronik**  
  - 约 350 名员工，管理团队包括 CEO、CTO、CFO 和首席商务官等[24][64][82][25]。  

- **EngineAI**  
  - 核心团队由来自全球顶尖高校和机构的专业人士组成，CEO 赵同阳具备丰富管理经验[5][36][13][14]。  
  - 公开资料未披露具体人数结构。

### 6.2 Physical AI 软件公司的团队画像

- **Covariant**：  
  - 创始团队包括 Peter Chen 与 Pieter Abbeel 等顶级学术背景的研究者[9][26][55][56]，技术团队以深度学习与强化学习专家为主。  

- **Intrinsic**：  
  - CEO Wendy Tan White 具有创业与 Alphabet 经验[57][58]，团队在企业软件与机器人技术上形成组合；  
  - 2025 年约 247 名员工，兼具产品、工程与销售团队[11][59][60]。  

- **Physical Intelligence**：  
  - 被 CapitalG 描述为“最强机器人 AI 团队”，成员来自 Google Research、DeepMind 与 UC Berkeley[19][30][23][52]；  
  - PitchBook 显示公司约 80 名员工，结构偏精干研究型与早期商业化团队[30][23]。  

### 6.3 团队演化：从研究到部署

- **Sanctuary AI**：  
  - 官方博客与新闻显示公司从以研发为中心向部署与商业化阶段转型，领导团队随之调整（Geordie Rose 卸任 CEO，James Wells 接任）[77][24][82][25]。  
  - 2026 年 3 月约 163 名员工，分布于六大洲[75][76][77]。  

- **Agility Robotics**：  
  - 引入运营与商业高管，配合 Digit 工厂量产，标志从“研究与工程公司”向“产品与运营公司”演化[76][77][78]。  

- **Tesla AI & Robotics**：  
  - 统一负责车辆与 Optimus 的自治系统开发，体现出“统一 AI 栈 + 多产品线”的组织结构，强化模型与软件在公司中的核心位置[31][67][68][69]。  

### 6.4 人才结构与区域分布

- Figure：2024 年约 60% 员工为工程岗位，且大量来自 MIT 等顶级院校[50][51]。  
- Physical Intelligence：约 80 人团队集中来自顶级 AI 与机器人机构[19][30][23][52]。  
- Sanctuary AI：163 名员工分布在六大洲，体现早期全球化人才配置策略[75][76][77]。

---

## 七、区域对比：中美欧日

### 7.1 中国：政策牵引与“模型 + 本体量产”

- 中国信通院《具身智能发展报告》与 IDC 把具身智能定位为“模型驱动、软件定义、硬件重构”的新一代智能机器人技术路径，以具身基础模型为核心“中枢”，强调感知–认知–决策–执行闭环与虚实融合训练[4][5][36]。  
- 政策上，中国在 2026 年发布更新的《人形机器人与具身智能标准体系》，覆盖关键部件、整机与系统应用[26][27]。  
- 产业层面，智元与宇树在通用人形与四足本体量产上实现突破，EngineAI 与傅利叶等在产线与场景拓展方面发力[5][36][20][16][85][71][74][72][73]。  

**特征**：政策与标准强力牵引，**模型 OS + 本体量产** 双向推动；在国内市场形成较完整的产业链。

### 7.2 美国：多元创业生态与模型/平台主导

- Figure、Agility、Apptronik、1X、Sanctuary、Covariant、Intrinsic、Physical Intelligence 等公司集中于美国[7][8][9][18][19][30][23][24][11]。  
- 技术路线多元：  
  - 具身大模型（Figure、Physical Intelligence）；  
  - 人形本体 + 仓储/制造（Agility、Apptronik）；  
  - AI 软件栈（Covariant、Intrinsic）；  
  - 遥操作示教 + 学习控制（1X、Sanctuary）。  

资本更偏好平台型与模型型企业，并重视创始团队的顶级学术与大型科技公司背景[9][26][18][19][30][23][11][59][60]。

### 7.3 日本：工业基础 + AI 软件

- Mujin 展示了日本在工业与物流场景中将传统机器人与 AI 软件结合的路径：MujinOS 用 AI 软件栈升级现有机器人系统[40][53][83][84]。  
- 与中国的人形本体量产与美国的平台生态相比，日本路径更强调“利用现有工业基础 + AI 软件赋能”。

### 7.4 欧洲及其他地区

- Intrinsic 虽属 Alphabet，但与欧洲机器人生态（如 KUKA）合作紧密[26][54][11][57]，体现了欧–美融合的“软件定义机器人”路线。  
- 软体机器人研究在全球分布较广，但产业化公司分布与区域领先性在现有证据中尚不清晰[42][43][20][16]。

---

## 八、展望与结论

### 8.1 技术与产业趋势（在证据范围内）

1. **具身基础模型将成为系统中枢**  
   多篇综述与产业报告均强调具身基础模型/具身大模型在感知–理解–规划中的核心作用[2][3][31][32][33][12][35][4][5]，产业中 Figure、智元与 Physical Intelligence 等已在这一方向上形成布局[28][45][29][47][18][19][30][23]。

2. **世界模型与虚实融合将成为工程标配**  
   世界模型与 sim2real 策略在复杂场景中提供可解释的决策与低成本训练[3][31][32][33][34][41][4][29]，未来在人形与工业机器人中有望成为标准组件。

3. **软硬协同与“软件定义本体”趋势确立**  
   中国信通院与 IDC 提出的“模型驱动、软件定义、硬件重构”与 Mujin、Covariant、Intrinsic 等公司的实践高度契合[40][53][9][26][54][4][5][36]，本体将围绕软件与模型需求迭代。

4. **人形机器人从研发 Demo 向标准化量产过渡**  
   智元、EngineAI、Agility 与宇树等已在产线与量产上取得进展[5][36][20][16][71][74][15][66][79]，结合中国的标准体系，意味着人形机器人产业将步入“标准化+量产+多场景部署”的阶段。

5. **安全与人机协作框架的重要性上升**  
   SAE 白皮书表明，部署安全、信任与人机协作将成为监管与工程实践的关键议题[27][36]，未来具身智能公司需要在技术与合规两方面构筑能力。

### 8.2 对投资人与产业研究者的启示

- **优先关注“模型 OS + 本体规模化”的双优型公司**：如智元（ERA‑42 + 远征系列）、Figure（Helix + 通用人形）与 Physical Intelligence（基础模型），这些公司在模型与本体两端构筑壁垒[28][45][71][74][29][47][18][19][30][23][52]。  
- **Physical AI 软件栈的跨硬件杠杆效应**：Mujin、Covariant、Intrinsic 等平台拥有天然的跨硬件与跨行业扩展能力，盈利路径更接近 SaaS/工业软件[40][53][9][26][54][11][59][60]。  
- **关注政策与标准环境**：中国在标准体系与政策上的布局将显著影响产业格局[26][27][4][5]，美国与欧洲则通过资本与大型科技公司塑造平台生态，日本通过产业基底与软件栈形成差异化路线[40][53][83][84][11]。  
- **持续监测团队结构与组织演化**：研发/硬件/运营团队结构、领导层变动与全球化人才配置是评估公司从 Demo 走向规模部署能力的重要指标[20][21][23][77][24][82]。

### 8.3 局限性与未来研究方向

- 由于缺乏全面的财务与技术披露，本报告在融资、估值与具体技术指标上只能给出部分样本与趋势，而非完整统计；  
- 区域对比以典型公司与政策文本为代表，不能完全覆盖所有重要参与者；  
- 未来研究需要结合更系统的数据库与企业披露，对不同技术路线的性能–成本–安全性进行标准化评估，并构建统一的“具身智能公司财务与运营指标库”。

---

## 参考文献

[1] Sam Altman’s OpenAI just made robotics its next frontier and it’s hiring to prove it https://techfundingnews.com/sam-altmans-openai-just-made-robotics-its-next-frontier-and-its-hiring-to-prove-it/

[2] Physical Intelligence raises $600M to advance robot foundation models https://www.therobotreport.com/physical-intelligence-raises-600m-advance-robot-foundation-models/

[3] 日均“吸金”超3亿， 具身智能杀疯了 https://auto.gasgoo.com/news/202604/9I70452827C601.shtml

[4] Embodied Intelligence Is Redefining Industrial Operations https://www.techaheadcorp.com/blog/how-embodied-intelligence-redefining-industrial-operation/

[5] A Comprehensive Survey on Embodied Intelligence https://www.sciopen.com/article/10.26599/AIR.2024.9150042

[6] Figure AI https://www.figure.ai/

[7] [PDF] 国外人形机器人产品梳理 https://pdf.dfcfw.com/pdf/H3_AP202311141610688991_1.pdf

[8] 3.0 人形机器人-具身智能 - 飞书文档 https://docs.feishu.cn/article/wiki/DmzWw8aNnig4QckQvF6cE4hSn1g

[9] 具身智能发展报告 - 中国信息通信研究院 http://www.caict.ac.cn/kxyj/qwfb/bps/202601/P020260130541978285206.pdf

[10] Welcoming Dar Sleeper as VP of Product & Design – 1X Tech https://www.1x.tech/discover/1x-welcomes-dar-sleeper

[11] 宇树科技股份有限公司首次公开发行股票并在科创板上市招股说明书 https://static.sse.com.cn/stock/disclosure/announcement/c/202603/002178_20260320_QY8F.pdf

[12] 20 Physical AI Companies to Watch in 2026 - RAISE Summit https://www.raisesummit.com/post/20-physical-ai-companies-to-watch-in-2026

[13] A Comprehensive Survey on World Models for Embodied AI https://arxiv.org/html/2510.16732v1

[14] Paper List and Resource Repository for Embodied AI https://github.com/HCPLab-SYSU/Embodied_AI_Paper_List

[15] 傅利叶FOURIER | 以机器人科技赋能生活 https://www.fftai.cn/

[16] Embodied Foundation Models at the Edge: A Survey of Deployment ... https://www.preprints.org/manuscript/202603.1293

[17] 国先中心：具身智能数据行业研究白皮书2026 https://www.sohu.com/a/997845448_468661

[18] 100+ Figure Ai Statistics: 2026 Verified Report – WifiTalents https://wifitalents.com/figure-ai-statistics/

[19] He's Building Robots That Will Live In Your Home | Bernt Bornich ... https://www.youtube.com/watch?v=61hUFIMV-uY

[20] A Survey on Vision-Language-Action Models for Embodied AI https://arxiv.org/html/2405.14093v6

[21] Beijing bets on embodied intelligence to secure structural power https://eastasiaforum.org/2026/04/23/beijing-bets-on-embodied-intelligence-to-secure-structural-power/

[22] Embodied AI in Action: Insights from SAE World Congress 2026 on Safety, Trust, Robotics, and Real-World Deployment https://arxiv.org/pdf/2605.10653

[23] Meet the Team at Sanctuary AI https://www.sanctuary.ai/blog/meet-the-team-at-sanctuary-ai

[24] Agility Robotics – LinkedIn https://www.linkedin.com/company/agilityrobotics

[25] Leadership – Apptronik https://apptronik.com/leadership

[26] 模型驱动，软件定义，硬件重构——IDC 解读2026年具身智能机器人 ... https://www.idc.com/resource-center/blog/%E6%A8%A1%E5%9E%8B%E9%A9%B1%E5%8A%A8%EF%BC%8C%E8%BD%AF%E4%BB%B6%E5%AE%9A%E4%B9%89%EF%BC%8C%E7%A1%AC%E4%BB%B6%E9%87%8D%E6%9E%84-idc-%E8%A7%A3%E8%AF%BB-2026%E5%B9%B4%E5%85%B7%E8%BA%AB/

[27] How Embodied AI Fits into the Future of Manufacturing https://www.automate.org/industry-insights/how-embodied-ai-fits-into-the-future-of-manufacturing

[28] 亏7.9亿却砸1.24亿年薪招人，宇树对手赌的是什么？ https://finance.sina.cn/2026-04-08/detail-inhtuupv9492514.d.html

[29] Figure AI – Wikipedia https://en.wikipedia.org/wiki/Figure_AI

[30] Sanctuary AI Announces Leadership Update... https://www.bctechnology.com/news/2024/11/12/Sanctuary-AI-Announces-Leadership-Update-Company-Co-Founder-Geordie-Rose-Leaving-CEO-Position.cfm

[31] ANSCER Robotics closes Series A round for industrial material handling https://www.therobotreport.com/anscer-robotics-closes-series-a-round-industrial-material-handling/

[32] EngineAI Launches Shenzhen Intelligent Manufacturing Base as First Batch of T800 Humanoid Robots Roll Off the Production Line to Begin Mass Delivery https://www.manilatimes.net/2026/05/29/tmt-newswire/pr-newswire/engineai-launches-shenzhen-intelligent-manufacturing-base-as-first-batch-of-t800-humanoid-robots-roll-off-the-production-line-to-begin-mass-delivery/2354348

[33] ‘The Great Replacement’: 5 robots replacing human workforce in 2026 https://www.wionews.com/photos/the-great-replacement-5-robots-replacing-human-workforce-in-2026-1780553633059

[34] Ubtech Robotics Navigates China’s Humanoid ID Rule as Manufacturing Costs Plunge to €13,000 https://www.ad-hoc-news.de/boerse/news/ueberblick/ubtech-robotics-navigates-china-s-humanoid-id-rule-as-manufacturing/69449233

[35] 智元向左，宇树向右：20家企业激战具身智能，谁代表了未来？ https://m.ofweek.com/ai/2026-03/ART-201700-8420-30683114.html

[36] Embodied AI: From LLMs to World Models [Feature] https://mn.cs.tsinghua.edu.cn/xinwang/PDF/papers/2025_Embodied%20AI%20from%20LLMs%20to%20World%20Models.pdf

[37] AI & Robotics | Tesla https://www.tesla.com/AI

[38] Humanoid Robots for Business: 2026 Guide - RobotLAB https://www.robotlab.com/humanoid-robots?srsltid=AfmBOop8KJYnpH7niV3e7I__oEExp0LHhlLgFWpeiub1xJYB34SCZdAK

[39] Physical AI at Work: How Mujin Redefined Automation Intelligence ... https://mujin-corp.com/resources/blog/mujin-modex-2026-physical-ai-at-work

[40] 2026年具身智能进入“上市大年”-钛媒体官方网站 https://www.tmtpost.com/7916254.html

[41] Humanoid robots work nonstop in package test https://www.aol.com/articles/humanoid-robots-nonstop-package-test-163051000.html

[42] Embodied AI with Foundation Models for Mobile Service Robots https://www.mdpi.com/2218-6581/15/3/55

[43] Embodied large language models enable robots to complete complex tasks https://www.nature.com/articles/s42256-025-01005-x

[44] Physical Intelligence (π) https://www.pi.website/

[45] 拆解智元：一台机器人，三份收入，一张资本网 https://m.36kr.com/p/3830251272939392

[46] 1X Technologies Revenue 2025: $222.5M ARR, $667.5M Valuation – GetLatka https://getlatka.com/companies/1x.tech

[47] Master Plan – Figure AI https://www.figure.ai/master-plan

[48] Figure AI – Bravo Victor Venture Capital https://bv.vc/team/figure-ai/

[49] Figure – LinkedIn https://www.linkedin.com/company/figure-ai

[50] Optimus (robot) – Wikipedia https://en.wikipedia.org/wiki/Optimus_(robot)

[51] 1X Business Breakdown & Founding Story – Contrary Research https://research.contrary.com/company/1x

[52] Sanctuary AI – LinkedIn https://ca.linkedin.com/company/sanctuaryai

[53] 首屆香港具身智能產業峰會暨智元APC2026香港舉行 - Yahoo 財經 https://hk.finance.yahoo.com/news/%E9%A6%96%E5%B1%86%E9%A6%99%E6%B8%AF%E5%85%B7%E8%BA%AB%E6%99%BA%E8%83%BD%E7%94%A2%E6%A5%AD%E5%B3%B0%E6%9C%83%E6%9A%A8%E6%99%BA%E5%85%83apc2026%E9%A6%99%E6%B8%AF%E8%88%89%E8%A1%8C-092700425.html

[54] A Strategic Analysis of the Future of AI and Robotics: From Industrial ... https://thecuberesearch.com/a-strategic-analysis-of-the-future-of-ai-and-robotics-from-industrial-efficiency-to-embodied-intelligence/

[55] Agility Robotics, Boston Dynamics see leadership changes https://www.therobotreport.com/agility-robotics-boston-dynamics-see-leadership-changes/

[56] CEO of Boston Dynamics to step down... https://www.thestar.com.my/tech/tech-news/2026/02/11/ceo-of-boston-dynamics-to-step-down-as-hyundai039s-robot-strategy-in-focus

[57] 宇树科技招股书数据解读 – X https://x.com/seclink/status/2035661551839990224

[58] 90后机器人创业者，再次获得近10亿元人民币融资 – Unitree Robotics https://www.unitree.com/cn/mobile/news/11

[59] 「站起来」赚钱的宇树，市值能冲破千亿吗？ – 21 经济网 https://www.21jingji.com/article/20260324/herald/9cf337344e78c525ae5ed957d2afd82c.html

[60] Join Us – Unitree Robotics https://www.unitree.com/cn/position

[61] Exploring Embodied Intelligence in Soft Robotics: A Review https://www.mdpi.com/2313-7673/9/4/248

[62] Embodied Intelligence Technology for Next-Generation Soft Robots https://www.espublisher.com/journals/articledetails/2073/

[63] Boston Dynamics – Wikipedia https://en.wikipedia.org/wiki/Boston_Dynamics

[64] How many employees work at Agility Robotics? – Revelio Labs https://www.reveliolabs.com/companies/agility-robotics/employees/

[65] Embodied AI: China's ambitious path to transform its robotics industry https://merics.org/en/report/embodied-ai-chinas-ambitious-path-transform-its-robotics-industry

[66] FOURIER – Robotics https://www.fftai.com/

[67] 具身智能发展报告 - 中国信息通信研究院 https://www.caict.ac.cn/kxyj/qwfb/bps/202408/P020240830312499650772.pdf

[68] Intrinsic https://www.intrinsic.ai/

[69] Wendy Tan White – Intrinsic https://www.intrinsic.ai/blog/authors/wendy-tan-white

[70] 一篇具身智能的最新全面综述！（下） https://www.iyiou.com/analysis/202410311081563

[71] Humanoid Robots 2026: Tesla Optimus, Figure 02 & NVIDIA Isaac ... https://www.meta-intelligence.tech/en/insight-physical-ai

[72] Peter Stone CV (Beyond Sim2Real: Leveraging Simulation in Support of Embodied World Models for Real-World Robot Learning entry) https://www.cs.utexas.edu/~pstone/cv/cv.pdf

[73] Real-world soft robot intelligence enabled by Sim2Real - JST AIP Network Co-Lab https://www.jst.go.jp/kisoken/aip/colab/en/researchers/

[74] AI & Robotics | Tesla https://www.tesla.com/en_ph/AI

[75] Sanctuary AI Company Overview – LeadIQ https://leadiq.com/c/sanctuary-ai/5d448125f45f783eced6ff5c

[76] Company and Team Update – Sanctuary AI https://www.sanctuary.ai/blog/company-and-team-update

[77] Company – Agility Robotics https://www.agilityrobotics.com/company

[78] Agility Robotics Strengthens Leadership Team https://www.agilityrobotics.com/content/agility-robotics-strengthens-leadership-team

[79] 加入我们 – 傅利叶FOURIER https://www.fftai.cn/career

[80] 傅利叶智能深度解析 – 艾邦机器人 https://www.aibangbots.com/a/5720

[81] The Global Swarm Robotics and Swarm Intelligence Market https://constable.blog/wp-content/uploads/The-Global-Swarm-Robotics-and-Swarm-Intelligence-Market.pdf

[82] Report: Agility Robotics' Business Breakdown & Founding Story – Contrary Research https://research.contrary.com/company/agility-robotics

[83] Apptronik Accelerates Commercialization with Key Executive Hires https://apptronik.com/news-collection/apptronik-accelerates-commercialization-with-key-executive-hires

[84] Apptronik – LinkedIn https://www.linkedin.com/company/apptronik-inc.

[85] 具身智能发展报告 - 北京人形机器人创新中心 https://x-humanoid.com/storage/website/2025/01-14/6785fd2145c36-1-27438.pdf

[86] 中国人工智能系列白皮书-具身智能(2026) https://finance.sina.com.cn/wm/2026-05-07/doc-inhwzvzm2910060.shtml
