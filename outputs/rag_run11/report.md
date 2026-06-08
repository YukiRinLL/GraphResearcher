## 引言

2022–2026 年间，具身智能（embodied intelligence）从传统机器人与强化学习研究，快速演化为围绕大模型、世界模型和人形机器人平台的产业化浪潮。学术综述普遍将具身智能界定为：在物理或虚拟“身体”中，通过感知—决策—行动闭环实现的智能系统，强调多模态感知、环境动力学建模和任务驱动控制的统一。[1]

在技术路线层面，近期重要综述与行业报告将机器人学习与具身智能基础模型大致归类为：视觉-语言-行动（Vision-Language-Action, VLA）与机器人基础模型路线、世界模型 + 分层控制路线、LLM 规划 + 低层控制路线、传统控制 + 学习模块混合路线，以及“互联网视频到机器人”方向。[1][2][3][4][5][6] 这些路线在模型架构、训练范式和软硬件一体化方式上存在显著差异。

本报告在 2022–2026 的时间窗口内，基于公开论文、综述与权威新闻/公司披露材料，梳理上述主要技术路线，并围绕 Figure、Google DeepMind、Covariant、Unitree、1X、Sanctuary、Agility 等代表性公司，分析其技术路径、产品进度、商业模式雏形、融资和核心团队背景。报告采用文献综述与公司案例分析相结合的方法，侧重技术与产业逻辑，而非完整的投融资数据库统计。对于存在口径差异的数据（如 Figure 累计融资、Agility 累计融资、Unitree 估值区间等），将显式披露不同来源的说法，并以“区间”“量级”等审慎表述处理不确定性。[7][8][9][10][11]

> 关键假设：  
> 1）“具身智能公司”主要指以通用人形机器人、世界模型 + 机器人基础模型等为核心的企业，非传统单用途机器人厂商；  
> 2）时间窗口默认涵盖 2022–2026 年公开信息，即便部分论文/报道在 2021 年启动、2026 年后续讨论；  
> 3）对未公开精确数字的融资/估值采纳“金额级别与区间”表述，不做点估。

---

## 第一章 技术路线总体图景

### 1.1 具身智能与大模型：研究视角

多篇 2024 年左右的具身智能与机器人学习综述表明，研究格局已经从经典“感知—认知—控制”三层架构，扩展到端到端深度强化学习、世界模型驱动的控制，以及以 VLM/VLA/LLM 为核心的基础模型系统。[1][2][3][4][5]

- 具身智能综合综述指出，当前具身智能研究覆盖从模块化三层架构到端到端深度强化学习和世界模型路线，并越来越多地整合多模态感知与大模型。[1]
- “Robot learning in the era of foundation models” 将机器人学习流程概括为：在互联网级多模态数据上自监督预训练，然后在机器人数据上通过模仿学习或强化学习微调，最后引入 RLHF 等人类反馈对齐方法。[2]
- 大模型赋能具身决策的综述将决策过程拆分为感知表示、任务理解、规划、控制和反馈学习多个阶段，高层由 LLM/VLM/VLA 承担任务理解与规划，低层由学习到的控制器执行动作。[3]

面向 VLA 模型的专门综述进一步给出“基础模型视角”：VLA 通常由视觉编码器、语言编码器和动作解码器/策略网络构成，可用行为克隆、强化学习、人类偏好优化和自监督学习等多种方式训练，数据来源包含人类视频、机器人轨迹和互联网多模态内容。[4] 具身 AI 数据综述则从数据流水线角度，将主流训练范式归纳为：生成式预训练（GP）→ 监督微调（SFT）→ 人类偏好对齐（RLHF/DPO）。[5]

结合这些综述与 2026 年针对机器人基础模型的专门综述，可以将 2022–2026 的具身智能技术路线抽象为若干互有交叉的主干方向。[6]

### 1.2 主要技术路线分类

#### 1.2.1 VLA / 机器人基础模型路线

VLA/机器人基础模型路线通过多模态 Transformer 或类似结构，将视觉、语言（或语音）和动作统一到一个端到端模型中，直接从视觉+语言输入生成动作 token 或电机指令。[4][6][12][13][14][15][16]

- 学术代表包括 Google DeepMind 的 RT-2：在互联网规模图文数据与机器人交互数据上联合训练，使模型从视觉和语言输入直接输出机器人动作 token，具备零/少样本泛化能力。[12][13][14]
- VLA 被定义为“输入视觉与语言指令、输出机器人电机动作的多模态基础模型”，常采用 encoder-decoder 或单一策略头结构，并在工业部署时与传统分层控制系统集成，以满足安全和可靠性要求。[4][15][17]
- 2025 年 VLA 综述将这一系列模型视为从“VLM + 独立策略网络”演化到统一 Transformer 架构，并进一步与世界模型和 LLM 规划结合，朝通用现实世界代理发展。[18]

公司层面，Figure 的 Helix 被明确定位为“generalist Vision-Language-Action model”，统一 Figure 人形机器人上的感知、语言理解与控制。[19][20] Covariant 的 RFM-1 和 Covariant Brain 则被描述为物流场景中的“机器人基础模型”和“通用机器人大脑”。[21][22][23] Unitree 提供 G1-D 等“端到端平台”，面向人形机器人基础模型开发。[24] AGIBOT 的 GO-2 被明确称为“embodied AI foundation model”，服务于自家机器人平台。[16]

#### 1.2.2 世界模型 + 分层控制路线

世界模型路线强调先学习一个能够预测环境视觉观测、动力学和语义的世界模型（latent dynamics、物理世界模型或符号世界模型），再在此模型上进行规划与控制，常与分层结构结合。[25][26][27][28]

- 世界模型综述定义了具身世界模型的多种形态，将其用于提升长时规划能力、样本效率和 sim-to-real 迁移能力。[25]
- DayDreamer（CoRL 2022）通过学习潜在世界模型并在其上规划，实现物理机器人上的样本高效学习，被作为世界模型 + 规划路线的代表。[26]
- PhysWM 项目则提出学习带因果结构的物理世界模型，再在该模型上使用最优控制或强化学习计算策略，体现了“先建模，后控制”的分层结构。[27]

产业实践中，此类方法往往与 VLA 或 LLM 规划耦合。例如，“Embodied AI: From LLMs to World Models” 文章提出“Embodied Foundation Model”框架，将 LLM 决策、世界模型和低层控制整合。[29] 1X 的技术栈中，1XWM 作为世界模型，Redwood 作为控制模型，NEO 作为人形平台，构成世界模型 + 控制 + 具身平台的组合。[30]

#### 1.2.3 LLM 规划 + 低层控制 / 多模态 Agent 路线

LLM 规划路线中，大语言模型承担高层计划与工具调用，低层控制由传统运动控制栈或独立学习控制器执行。[3][31][32][33][34]

- 大模型赋能具身决策的综述与 NAACL 2025 教程总结了“LLM 作为 planner 或 tool user”的典型架构：LLM 通过标准化环境 API 接收观测、输出高层命令或工具调用，环境模拟器或物理机器人通过独立控制栈执行。[3][32][34]
- NeurIPS 2024 的 “Embodied Agent Interface” 提出标准接口：LLM 通过 API 接收环境状态并输出高层指令，低层精细动作由独立控制模块执行；实验结果表明 LLM 更适合高层推理与工具选择，而非精细电机控制。[33][35]
- ELLMER 框架（Nature 2025）将 LLM 用于层次任务分解，子任务由模仿学习得到的低层技能执行，构成“LLM 规划 + imitation-control”的具身层次策略。[31]

该路线强调高层与低层解耦，以提高系统可解释性与安全性。[31][32][33]

#### 1.2.4 传统控制 + 学习模块混合路线

大量工业与服务机器人系统仍以传统工程化栈为主：视觉感知与语义理解可由基础模型提供，但高速闭环控制与导航仍依赖经典规划与控制算法。[35][15][17]

- 移动服务机器人上的具身 AI 研究指出，预训练视觉或 VLM 模型主要负责语义感知和语言理解，导航与操作则由已有导航、操控模块执行。[35]
- 工程实践中，VLA 等基础模型常与经典分层控制结合：VLA 提供任务级决策与高层动作建议，motion planning 和闭环控制则由传统算法承担，以满足性能和安全标准。[15][17]

Boston Dynamics 等厂商在公开材料中强调高鲁棒性感知、MPC/反馈控制与 RL/模仿学习模块的结合；“Humanoid Robots at work” 论文评估工业场景的人形机器人应用时，也突出工程可靠性与安全规范的重要性。[36][37]

#### 1.2.5 互联网视频到机器人路线

互联网视频到机器人路线旨在通过大规模人类视频和多模态数据，为机器人学习提供“通用先验”，通过表示对齐与 latent action 学习，将人类动作迁移到机器人策略。[28][38][39][8]

- “From Human Videos to Robot Manipulation” 综述提出 “representation bridges” 概念，将人类和机器人在形体与动作空间上的差异通过中间表示对齐，使互联网规模人类视频可用于训练 VLA 表示并对齐到机器人动作空间。[28]
- “Latent Action Pretraining from Videos” 采用两阶段流程：先在无标注视频上训练动作量化模块得到离散 latent action token，再用这些 token 作为中间表示训练机器人策略，提高数据效率和泛化。[38]
- JAIR 的 “Towards Generalist Robot Learning from Internet Video” 系统梳理了从网络视频学习通用机器人策略的工作，指出需要通过动作对齐、表示学习和视频-语言模型等手段解决人-机形体与视角差异问题。[39][8]

该方向常与 VLA 和世界模型方法结合，被视为扩展训练数据规模和提升泛化能力的关键路径。[4][25][28][39]

### 1.3 训练范式与流水线

跨路线观察，具身智能基础模型的训练范式呈现高度收敛趋势：[2][4][5][25][6]

1. **生成式预训练 (GP)**：在互联网图像-文本、视频、语言数据及模拟器日志上自监督或生成式预训练（VLM / VLA / 世界模型），学习通用感知与世界知识表示。[2][4][5][25]
2. **监督微调 (SFT)**：在机器人演示、轨迹数据、任务标注数据上进行行为克隆或强化学习微调，适配具体机器人形体与任务，包括离线/交互式模仿学习和 RL。[2][4][5][40][21]
3. **人类偏好对齐 (RLHF/DPO 等)**：通过人类偏好比较、在线纠正等方式，对基础模型策略进行偏好优化，提升安全性、稳定性与人类价值对齐。[2][5][29]

具身数据综述明确将许多系统的训练管线描述为 GP→SFT→RLHF/DPO 三阶段。[5] 基础模型与 VLA 综述也分别从模型与数据视角给出类似结构。[2][4][6]

---

## 第二章 路线一：VLA / 机器人基础模型 + 通用平台

### 2.1 典型代表与平台形态

本路线的特征是：通过统一的 VLA/基础模型作为“机器人大脑”，在多种机器人硬件平台上实现通用任务执行。代表性系统包括 Google RT 系列、Figure Helix + Figure 01/03、Covariant RFM-1/Brain，以及 Unitree G1-D 等端到端平台，以及 AGIBOT GO-2。[19][20][12][13][14][15][17][16][36][24][41][23][42]

#### 2.1.1 Google DeepMind RT 系列

RT-2 项目页与系列博客说明：RT-2 是一个 Vision-Language-Action 模型，通过将互联网规模图像-文本数据与机器人交互数据结合训练，实现从视觉和语言输入直接输出机器人动作 token。[12][13][14]

- 输入：视觉观测 + 文本/语言指令。
- 输出：离散动作 token，经解码后控制机器人执行任务。[13]
- 训练：联合使用 Web 图像-文本数据和实验室机器人数据，提升未见任务上的零/少样本泛化能力。[12][13][14]

RT-2 及后续 RT-X 代表了从 VLM 向 VLA 的典型演进，成为 VLA 路线的标杆之一。[12][13][14][18]

#### 2.1.2 Figure：Helix 与 Figure 01–03

Figure AI 自 2022 年成立以来，持续迭代人形机器人与 VLA 模型：[43][44][45]

- 产品线：Figure 已开发三代人形机器人 Figure 01–03，以及两代 Helix VLA 模型（Helix 01–02），可同时控制多台机器人。[43][44]
- Helix：官方称 Helix 为 “generalist VLA model”，用于通用人形机器人 Figure，统一视觉感知、语言理解和控制。[19]
- TechCrunch 报道将 Helix 描述为 Figure 机器人的“大脑”，结合视觉数据与语言/语音指令实时生成动作，部署场景覆盖家务和工厂任务。[20][33]

Figure 的技术路线可概括为：以 Helix VLA 为核心的大模型控制栈，配合迭代中的 Figure 01–03 硬件平台，从工厂到家庭推进通用人形机器人应用。[19][20][43][45]

#### 2.1.3 Covariant：RFM-1 与 Covariant Brain

Covariant 的公司博客与分析文章将 Covariant Brain 描述为通用机器人大脑，服务于仓储等多种物流场景。[21][22][23]

- Covariant Brain：作为统一的云端感知与决策模块，可控制多种物流机器人系统。[21]
- RFM-1：被称为“机器人基础模型”，为多任务物流操作提供类人推理与决策能力。[22]
- 风险投资分析将其路线概括为：以基础模型为核心的云端 AI 服务，通过与机器人硬件集成，实现多场景的自动化操作。[23]

尽管公开资料未详细披露网络结构，但整体符合 VLA/基础模型路线的特征。[21][22][23]

#### 2.1.4 Unitree：G1-D 端到端平台与估值

Unitree 提供 G1-D 等面向人形机器人基础模型开发的端到端平台，其产品面对开发者和企业客户，支持在通用人形硬件上开发与部署 VLA/基础模型。[24]

在资金与市场地位方面：

- 2022 年 4 月，Unitree 完成“数亿元人民币”的 Series B 融资。[42]
- Forbes 报道称 2025 年 Series C 后 Unitree 估值约 120 亿元人民币（约 17 亿美元），目标在科创板 IPO。[46]
- PANews 文章称 Series C 后估值“超过 100 亿元人民币”，并讨论投资收益。[47]
- Tracxn 数据显示 Unitree 共完成 6 轮融资，总额约 1.55 亿美元，Series B 为最大单轮。[48]
- KraneShares 报告指出 2025 年中期估值约 17 亿美元，IPO 目标估值区间 30–70 亿美元。[11]

尽管不同来源在估值表述上存在差异，但一致指向：2025 年后 Unitree 进入十亿美元级估值，是中国四足/人形机器人与具身智能平台的重要参与者。[42][46][47][48][11]

#### 2.1.5 AGIBOT：GO-2 具身 AI 基础模型

Robot Report 报道 AGIBOT 发布 GO-2 基础模型，明确称其为“embodied AI foundation model”，用于打通从感知到控制的“最后一公里”，面向企业级应用。[16] 这表明中国厂商中也出现了以基础模型为核心、支持多机器人平台的 VLA/基础模型路线。

### 2.2 模型架构与训练范式

跨上述系统，VLA/基础模型路线在架构与训练上具有共性：

1. **多模态编码 + 动作解码**  
   - VLA 模型由视觉编码器、语言编码器和动作解码器/策略网络构成，常使用 Transformer 进行序列建模。[4]
   - VLA 被定义为接收视觉与语言输入、输出机器人电机动作的多模态基础模型。[15]

2. **多源数据联合训练**  
   - RT-2 使用 Web 图像-文本数据与机器人交互数据联合训练，实现跨任务与跨场景泛化。[12][13][14]
   - VLA 和具身数据综述都指出：VLA 模型训练采用混合数据集，包含人类视频、机器人轨迹和互联网多模态内容。[4][5]

3. **GP→SFT→偏好对齐流水线**  
   - 机器人基础模型综述和数据综述指出，训练过程常采用生成式预训练、任务数据微调和人类偏好优化三阶段结构。[2][5][6]

在工业落地中，VLA/基础模型通常与传统控制栈集成，以兼顾通用性与安全性。[15][17]

### 2.3 产品进度与商业化雏形

#### 2.3.1 Figure：从工厂到家庭

Figure 的产品与部署进度在维基和媒体中有较详细记录：[43][44][49][50][51][52][53]

- Figure 01：面向手工劳动，初期聚焦物流与仓储场景。[49]
- BMW 合作：2024 年 Figure 与 BMW 合作，在美国 Spartanburg 汽车制造厂部署人形机器人，从事生产相关任务。[50]
- BotQ 制造设施：截至 2025 年，Figure 开始建设 BotQ 制造设施，规划年产 12,000 台人形机器人。[52]
- Figure 03 与家庭场景：2026 年 Figure 机器人展示执行家务工作的能力，并在白宫活动中公开亮相。[53]

商业模式方面，公开资料未给出具体收费结构，[9] 但 BMW 工厂部署、标杆客户订单和家务演示表明 Figure 正沿“工业标杆 + 家用扩展”的路径推进商业化。[19][20][43][50]

#### 2.3.2 Covariant：物流自动化与云端基础模型

Covariant 长期聚焦物流自动化，通过 Covariant Brain 和 RFM-1 提供“机器人基础模型”能力。[21][22][23]

- 产品与应用：服务于仓储抓取、分拣等多任务场景。
- 商业模式：以云端基础模型服务 + 软硬件系统为核心，为物流机器人车队提供识别、规划与控制能力。[21][22][23]

这一模式体现出“软件/模型 + RaaS”的特征。

#### 2.3.3 Unitree/AGIBOT：硬件平台 + 基础模型能力

Unitree 通过四足与人形平台构建低成本硬件基础，再引入基础模型与 VLA 能力。[24][42][46][47][48][11]

- G1/G1-D：面向研究与产业客户的人形平台，支持端到端基础模型开发与部署。[24]
- 商业路径：提供硬件平台与配套软件栈，定位为“人形机器人平台供应商”，而非单一应用集成商。

AGIBOT 的 GO-2 则更强调基础模型产品化，定位为企业级具身 AI 基础模型。[16]

### 2.4 融资与团队概况（概述）

#### 2.4.1 Figure 融资演进与统计差异

Figure 的融资路径相对清晰，但不同二级数据源在“累计融资”口径上存在差异：[7][8][51][10][54][55]

- 2023 年 5 月：约 7,000 万美元（Parkway 领投，Sam Altman 个人约 2,000 万美元）。[54]
- 2024 年 2 月：6.75 亿美元 Series B，投后估值约 26 亿美元。[52][56][55]
- 2025 年 9 月：超过 10 亿美元 Series C，投后估值 390 亿美元。[7][10]
- Startup Intros：累计融资约 18 亿美元。[8]
- WifiTalents：称累计融资超过 25 亿美元。[41]

保守表述是：截至 2025 年，Figure 累计融资至少在 18 亿美元以上，部分统计认为已超过 25 亿美元。[7][8][41]

团队方面，Figure 由 Brett Adcock 于 2022 年创立，他担任 CEO。[56][45] WifiTalents 称公司约 140 名员工，约 60% 为工程岗位，许多拥有包括 MIT 在内的顶尖高校博士学位。[55]

---

## 第三章 路线二：世界模型 + 分层控制

### 3.1 世界模型路线的技术内涵

世界模型综述将具身世界模型定义为：在潜在、物理或符号空间中同时捕捉环境视觉、动力学与语义，用于预测和规划。[25] 按建模方式可分为：

- 潜在动力学世界模型（如 Dreamer/DayDreamer）；
- 物理知识驱动的世界模型（如 PhysWM）；
- 符号/关系世界模型。

这些模型用于支持长时规划、提高样本效率和 sim-to-real 迁移。[25][26][27]

DayDreamer 被列为代表性 2022 方法，通过学习潜在世界模型与规划结合，实现物理机器人技能学习。[26] PhysWM 则强调学习具有因果结构的物理世界模型，再在其上使用最优控制或 RL 计算策略。[27]

### 3.2 1X：世界模型 + Redwood + 人形机器人

XMAQUINA 的公司故事文对 1X 的技术栈给出具体描述：[30]

- 1XWM：1X 自研世界模型，是一个端到端神经网络，将视觉、语言和运动控制融合，承担环境建模与性能评估功能。
- Redwood：通过 1XWM 训练出的控制模型，用于控制 NEO 人形机器人执行现实世界任务。
- 1XWM 还被用来构建机器人 scaling law，并作为世界模型为任务预测与规划提供基础。

因此，1X 的路线可视为“世界模型 + 控制 + 人形平台”的组合，并在高层可能再结合 LLM/多模态模块。[30]

### 3.3 研究线索与产业意义

DayDreamer 和 PhysWM 等研究工作尚以学术实验为主，但它们验证了世界模型在提高样本效率、支持长时规划方面的潜力。[25][26][27] 这些方法为产业系统中的世界模型模块提供理论基础，例如 1X 的 1XWM 与行业综述中提出的 Embodied Foundation Model 架构。[29][6][30]

---

## 第四章 路线三：LLM 规划 + 低层控制 / 多模态 Agent

### 4.1 LLM 规划架构与接口标准

LLM 作为高层 planner 或 tool user 的路线，在多篇综述与教程中被系统讨论：[3][57][32][33][34]

- “Embodied Foundation Model” 框架将 LLM 决策、世界模型和低层控制统一，强调 LLM 负责高层任务分解与工具调用。[29]
- NAACL 2025 教程和 “Towards Embodied Agentic AI” 评述将 LLM-based agents 按“纯对话代理—工具增强代理—具身 agentic 系统”分类，具身系统通过标准化环境 API 与传感器/执行器互动。[32][34][58]
- “Embodied Agent Interface” 提出标准接口：LLM 通过 API 接收环境状态，输出高层命令或工具调用，低层精细动作由独立控制器执行；实验结果显示 LLM 更适合高层推理而非低层控制。[33][35]

该路线强调模块化，将高层推理与低层控制解耦，以便于升级与安全控制。[32][33][58]

### 4.2 ELLMER：层次模仿与 LLM 规划

ELLMER 框架展示了 LLM 规划 + 模仿控制的典型实例：[31]

- LLM 负责理解语言任务并进行层次任务分解；
- 低层技能通过模仿学习训练，执行具体子任务；
- 系统能根据环境反馈修正计划，完成复杂多步任务。

这表明 LLM 可以作为具身层次策略的“框架搭建者”，而控制细节仍依赖专门学习到的技能。[31]

### 4.3 Embodied Agent Interface 与基准化进展

“Embodied Agent Interface” 提供了用于评估 LLM 在具身任务中表现的标准接口与基准：[33]

- 接口设计：LLM 接收环境观测与任务描述，输出高层指令或工具调用，控制层负责具体动作。
- 评估结果：LLM 在多步规划和工具使用上表现良好，但在精细动作控制方面能力有限。
- 结论：支持采用“LLM 规划 + 独立控制”的模块化架构。[33][35]

---

## 第五章 路线四：传统控制 + 学习模块混合与工程化路线

### 5.1 工程现实中的混合架构

尽管大模型和世界模型发展迅速，大量工业与服务机器人仍以传统工程化栈为主，尤其在安全与实时性要求极高的应用中。[35][15][17][36]

- 移动服务机器人研究指出，预训练视觉或 VLM 模型主要用于语义感知和语言理解，导航与操控由传统模块承担。[35]
- 工程实践强调，在工业部署中，VLA 等基础模型需要与经典分层控制集成：VLA 提供高层决策与策略建议，运动规划与闭环控制由成熟算法负责，以满足安全与可靠性要求。[15][17]

### 5.2 工业与物流场景的工程约束

“Humanoid Robots at work” 综述讨论了工业现场的人形机器人应用，强调当前人形机器人更多作为“增强型自动化设备”，其控制架构仍重视安全边界、冗余设计和人机协同规范。[37] 因此，在短期内，许多工业人形/移动机器人会采用混合架构，将感知与规划部分逐步引入大模型和学习模块，而底层控制与安全机制仍以传统工程栈为主。[35][15][37]

---

## 第六章 融资格局与商业化进展

### 6.1 Figure：多轮大额融资与估值跃迁

如前所述，Figure 的融资路径可以总结为早期轮 + 大额 B 轮 + 超 10 亿美元 C 轮，但累计融资数据存在冲突。[7][8][51][10][54][55]

- 2023 年 5 月：约 7,000 万美元（Parkway 领投，Sam Altman 个人约 2,000 万美元）。[54]
- 2024 年 2 月：6.75 亿美元 Series B，投后估值约 26 亿美元。[52][56][55]
- 2025 年 9 月：超过 10 亿美元 Series C，投后估值 390 亿美元。[7][10]

累计融资方面：

- Startup Intros：约 18 亿美元。[8]
- WifiTalents：称累计融资超过 25 亿美元。[41]

由于二级数据库对未披露细节的估算不同，本报告仅给出“至少 18 亿美元、可能超过 25 亿美元”的区间表述。[7][8][41]

### 6.2 1X：OpenAI Startup Fund 与 Series B

1X 的融资路径相对一致：[59][60]

- 2023 年 3 月：OpenAI Startup Fund 领投 2,350 万美元 Series A。[60]
- 2024 年 1 月：1 亿美元 Series B，由 EQT Ventures 领投，Samsung NEXT 与 Nistad Group 等参投。[59]

维基条目称 1X 累计融资超过 1.25 亿美元，与上述轮次规模相符。[60]

### 6.3 Sanctuary：政府与产业资金双轮驱动

Sanctuary AI 的融资兼具风投与政府创新基金特征：[61][62][36][63][64]

- 2022 年 3 月：7,550 万加元（约 5,850 万美元） Series A，投资方包括 Bell、Magna、Export Development Canada、Verizon Ventures 等。[61][36][63]
- 2022 年 11 月：加拿大政府 Strategic Innovation Fund 提供 3,000 万加元无稀释支持。[62][64]
- Dealroom 统计包括 2024 年来自 Accenture Ventures、BDC Capital 和 InBC 的战略投资，整体融资规模约 1 亿美元量级。[36]

这表明政府资金与产业资本共同支撑了其人形机器人与 Carbon 基础模型路线。[61][62][36]

### 6.4 Agility Robotics：人形物流的融资分歧

Agility 的官方披露与数据库记录存在显著差异：[49][50][51][52][53]

- 官方：2022 年完成 1.5 亿美元 Series B，用于扩大量产 Digit。[49]
- Sacra：称 2025 年 3 月左右完成 4 亿美元 Series C，post-money 估值约 21.2 亿美元，累计融资约 6.41 亿美元。[50][52]
- Startup Intros：总融资约 2.88 亿美元，最近一轮为 2024 年 10 月 1.1 亿美元 Series C。[51]
- LinkedIn 分析文章称 Agility 正以 17.5 亿美元 pre-money 筹集 4 亿美元 C 轮。[53]

在缺乏统一官方披露的情况下，安全的结论是：Agility 在 2024–2025 年期间完成一笔规模在 1.1–4 亿美元区间的数据不一致的 C 轮，累计融资至少在 2–3 亿美元以上，部分来源认为已超过 6 亿美元。[49][50][51][52][53]

### 6.5 Unitree 与中国厂商：估值与 IPO 预期

Unitree 在 2022–2025 年间完成多轮融资并进入十亿美元估值区间。[42][46][47][48][11]

- 2022 年 Series B：“数亿元人民币”规模。[42]
- 2025 年 Series C：Forbes 报道估值约 120 亿元人民币（约 17 亿美元），PANews 称“超过 100 亿元人民币”。[46][47]
- Tracxn：总融资约 1.55 亿美元。[48]
- KraneShares：2025 年中期估值约 17 亿美元，IPO 目标估值 30–70 亿美元。[11]

尽管不同来源存在差异，但整体指向：Unitree 已成为估值 10 亿美元以上的人形/四足机器人平台公司。

AGIBOT 等中国厂商也在发布 GO-2 等具身 AI 基础模型，表明国内资本市场开始支持“硬件 + 基础模型”一体路线。[16]

### 6.6 资本热度与投资偏好

综合 Figure、1X、Sanctuary、Agility、Unitree 等公司，可观察到以下特征：

- 单轮金额：北美头部公司单轮融资普遍在 0.5–10 亿美元区间。[7][61][59][49][52]
- 估值：Figure C 轮估值 390 亿美元，[7][10] Agility C 轮估值约 20 亿美元，[50][52] Unitree 估值约 17 亿美元并有更高 IPO 预期。[46][11]
- 投资者：包括 OpenAI Startup Fund、Microsoft、NVIDIA 等 AI/大厂资金，政府基金，以及传统风投与产业基金。[7][61][62][59][10][63][64]

资本显著偏好“基础模型 + 通用人形/物流机器人 + 标杆客户/政府支持”的组合，同时二级数据源之间的冲突提示在定量比较时需谨慎处理。[7][8][41][50][51][10]

---

## 第七章 核心团队与人才流动格局

图谱中关于所有公司核心团队的详细资料仍不完整，但现有证据反映出一些共性模式。

### 7.1 Figure：创业者背景与工程团队

Figure 由 Brett Adcock 于 2022 年创立，他担任 CEO。[56][45] WifiTalents 统计称，Figure 截至 2024 年中约有 140 名员工，约 60% 为工程岗位，许多拥有包括 MIT 在内的顶尖高校博士学位。[55] 这表明 Figure 在机器人、机器学习和控制方向上汇聚了较强的技术人才。

关于 CTO 角色，图谱中主要基于二级资料与社区讨论对 Jerry Pratt 等技术负责人有所提及，但缺乏权威官方声明，且 Reddit 等社区帖子称其为 CTO 的说法尚未得到严格佐证。[41] 鉴于来源层级差异，本报告不将“Figure 当前 CTO”作为确定性结论。

### 7.2 1X：世界模型团队与 OpenAI 生态

1X 的主要投资方包括 OpenAI Startup Fund、EQT Ventures、Tiger Global 等。[59][60] 公司故事文强调 1XWM 与 Redwood 构成其技术核心。[30] 虽然图谱未列出完整管理层名单，但“世界模型 + 人形”路线与 OpenAI 相关资本背景共同表明，其核心团队在机器人学习、大模型和系统工程方面具备较强积累。

### 7.3 Sanctuary：学术与产业交叉团队

Sanctuary 的投资方包括 Bell、Magna 和加拿大政府创新基金，反映出其管理团队在硬件、AI 和政策资源上的多方协同能力。[61][62][36][63][64] 图谱未详细列出各位创始人与 CTO 的教育背景，但投资结构与技术定位（Phoenix 人形机器人与 Carbon 基础模型）说明其团队在通用人形机器人与具身 AI 路线上的技术与产业经验较为丰富。

### 7.4 其他公司与人才流动模式（概述）

图谱中关于 Agility、Unitree、Apptronik、Boston Dynamics 等公司的核心团队信息点状散布，整体不足以重建完整的人员时间线与职责结构，但可观察到几个趋势：

- 人才来源集中于顶尖高校、自动驾驶/机器人公司和大模型公司；
- 团队构成普遍包括机械、电气、控制、感知、机器学习、软件与生产运营等跨学科角色；
- 部分公司（如 Unitree）通过 IPO 准备阶段的报道披露创始人与高管的工程背景与专利数量，表明以工程落地为核心竞争力。[42][46][47][48][11]

由于多个公司在 CTO 头衔与时间线方面存在未解冲突（例如 Agility 与 Unitree 的 CTO 称谓在不同报道中的差异），本报告不对这些职务安排给出唯一结论。

---

## 结论与展望

### 8.1 2022–2026 的关键拐点

综合上述证据，2022–2026 年全球具身智能在技术与产业层面经历了几个重要拐点：

1. **技术路线清晰化**  
   VLA/机器人基础模型、世界模型 + 分层控制、LLM 规划 + 低层控制、传统控制 + 学习模块混合以及互联网视频到机器人等主线逐渐成型，并在综述中被系统分类。[1][4][25][28][29][6][39]

2. **基础模型范式确立**  
   通过 GP→SFT→RLHF/DPO 的流水线，结合多模态大模型、机器人轨迹和人类偏好数据，成为机器人学习的主流范式。[2][4][5][6]

3. **通用人形平台与标杆部署**  
   Figure、Agility、1X、Sanctuary、Unitree 等公司在工厂、物流和家庭场景中开始标杆部署，推动人形机器人从实验室走向实际生产与服务环境。[20][43][49][50][52][53][42][46]

4. **资本与产业共振**  
   多家企业在短时间内获得数亿美元乃至十亿美元级的融资，估值进入 10 亿至数百亿美元区间，反映资本与产业对“具身智能 + 基础模型 + 通用机器人”组合的强烈信心。[7][61][59][49][50][46][11]

### 8.2 各路线的优势与不确定性

- **VLA/基础模型路线**：在任务泛化和“从互联网知识到机器人行为”的迁移能力上具有优势，代表系统如 RT-2、Helix、RFM-1/Brain、GO-2 等。[19][20][12][13][14][21][22][16] 但需要大量多模态数据和工程化的安全/实时性解决方案。[15][17]
- **世界模型 + 分层控制**：在样本效率、长时规划和 sim-to-real 上具有潜在优势，代表系统包括 DayDreamer、PhysWM 与 1XWM + Redwood。[25][26][27][30] 但在大规模工业部署上的实践案例相对有限。
- **LLM 规划 + 低层控制**：提供强大的语言理解与高层规划能力，适合复杂任务和工具调用场景，但当前 LLM 在精细控制方面存在局限，需要与专门控制模块结合。[31][29][32][33]
- **传统控制 + 学习模块混合**：在安全与可靠性上仍是许多工业/物流系统的主选，易于通过局部引入学习模块逐步升级，但在通用性与跨任务迁移方面可能面临基础模型路线的竞争压力。[35][15][37]
- **互联网视频到机器人**：通过表示桥与 latent action 学习，有望扩大可用数据规模，降低机器人数据采集成本，但在人-机形体差异、对齐质量和安全可控性上仍存挑战。[28][38][39][8]

### 8.3 数据冲突与证据不足

本报告在撰写过程中注意到多处关键冲突与局限：

1. **Figure 累计融资**：不同二级来源在 18 亿美元与 25+ 亿美元之间给出不同估计；仅 C 轮（>10 亿美元）与 B 轮（6.75 亿美元）及早期轮（约 7,000 万美元）相对确定。[7][8][41][51][54][55]
2. **Agility 累计融资与 C 轮规模**：Sacra 与其他媒体报道给出的 C 轮与累计融资数字明显高于 Startup Intros 等数据库，表明后者更新滞后或口径不同。[49][50][51][52][53]
3. **Unitree 估值与总融资**：Forbes/PANews、Tracxn 与 KraneShares 对 Unitree 估值与总融资存在量级接近但数值不同的差异，提示在使用具体数字时需采用区间表述。[42][46][47][48][11]
4. **团队信息不完整**：特别是 Tesla Optimus、Boston Dynamics、Apptronik 与多家中国/日本/欧洲厂商的核心团队背景和职务演变，图谱数据不足以形成完整对比。

为保持结论稳健，本报告在涉及上述数据时尽量采用“区间”“量级”“至少”等词汇，并在涉及团队职务时避免在冲突点上给出唯一结论。

### 8.4 展望

展望 2026 年之后，具身智能的发展可能沿以下方向演进：

- **Embodied Foundation Model 一体化**：更多系统将 VLA、世界模型、LLM 规划与低层控制整合为统一的“具身基础模型”，通过工具使用、自我改进和跨形体迁移，实现更高程度的通用性。[25][26][28][31][29][6][30]
- **多机器人、多场景、多任务数据平台化**：大规模、多场景的机器人数据集将继续扩张，互联网视频、模拟器和真实机器人轨迹的融合将成为常态。[2][4][5][28][39][8]
- **工业与监管环境适配**：随着人形与具身系统进入工厂与公共空间，安全、合规与责任划分将推动传统控制与基础模型之间的工程融合，以及更加严格的评估与认证框架。[33][35][15][37]
- **人才与生态竞争加剧**：由顶尖学术、AI 大厂和创业公司构成的人才流动格局，将继续推动技术快速演进，同时也可能导致技术与资本向少数平台集中，对中小企业形成压力。[56][55][30][61]

总体而言，2022–2026 年是具身智能从“多路线探索”走向“基础模型范式”与“通用人形平台”的关键窗口期。不同技术路线之间正在形成互补：VLA、世界模型、LLM 规划和传统控制并非互斥，而是以不同组合方式广泛共存。未来几年，这些组合在大规模商业部署中的表现，将决定具身智能能否真正成为下一代通用计算与自动化基础设施。

---

## 参考文献

[1] Figure AI https://www.figure.ai

[2] Ramping Figure 03 Production https://www.figure.ai/news/ramping-figure-03-production

[3] Figure AI - Wikipedia https://en.wikipedia.org/wiki/Figure_AI

[4] Figure AI Stock: $39B Valuation — Is It a Buy? https://tsginvest.com/figure-ai

[5] Figure AI Statistics https://wifitalents.com/figure-ai-statistics

[6] Agility Robotics raises $150M Series B led by DCVC and Playground Global https://www.agilityrobotics.com/content/agility-robotics-raises-150m-series-b-led-by-dcvc-and-playground-global

[7] A Complete Guide To Unitree Robotics’ 2026 IPO, Why It Matters For … https://kraneshares.eu/a-complete-guide-to-unitree-robotics-2026-ipo-why-it-matters-for-star-market-etf-kstr-humanoid-robotics-etf-koid/

[8] 90后机器人创业者，再次获得近10亿元人民币融资 - Unitree Robotics https://www.unitree.com/cn/news/11

[9] Large Model Empowered Embodied AI: A Survey on Decision ... https://arxiv.org/html/2508.10399v1

[10] From Human Videos to Robot Manipulation: A Survey on Scalable Representation Bridges for VLA Models https://arxiv.org/html/2606.00054v1

[11] NAACL 2025 Tutorial Proposal: Foundation Models meet Embodied ... https://aclanthology.org/2025.naacl-tutorial.3.pdf

[12] China's Robot Maker Unitree Valued At $1.7 Billion In Series C Round https://www.facebook.com/forbes/posts/unitree-robotics-a-hangzhou-based-maker-of-humanoid-robots-whose-founder-recentl/1098139712176018/

[13] Half of the investment community is grateful to Yushu. https://www.panewslab.com/en/articles/019d187e-3dac-7521-92af-26eaecf05bb2

[14] Elon Musk claims Tesla is buying more training compute for humanoid robot, Optimus https://www.datacenterdynamics.com/en/news/elon-musk-claims-tesla-is-buying-more-training-compute-for-humanoid-robot-optimus/

[15] 傅利叶宣布已完成新一轮融资，E系列融资总额近8亿 https://www.fftai.cn/about-medium-company/32

[16] 傅利叶智能| 项目信息 - 36氪 Pitchhub https://pitchhub.36kr.com/project/1678292892775424

[17] 傅利叶智能完成E轮融资，多家投资方共同注资 - 亿欧 https://www.iyiou.com/data/202501071087583

[18] Tesla humanoid robots rival Apptronik raises $350 million funding https://www.cnbc.com/2025/02/13/tesla-humanoid-robots-rival-apptronik-350-million-funding-round-google.html

[19] Agility Robotics valuation, funding & news | Sacra https://sacra.com/c/agility-robotics/

[20] Agility Robotics: Funding, Team & Investors | Startup Intros https://startupintros.com/orgs/agility-robotics

[21] Sanctuary AI secures strategic financing to advance AI in humanoid robotics https://www.womenincanadianmanufacturing.com/sanctuary-ai-secures-strategic-financing-to-advance-ai-in-humanoid-robotics/

[22] Sanctuary AI company information, funding & investors - Dealroom.co https://app.dealroom.co/companies/sanctuary_ai

[23] Latent Action Pretraining from Videos https://openreview.net/forum?id=VYOe2eBQeh

[24] 宇树科技IPO获受理估值127亿元 - 证券市场周刊 https://static.weeklyonstock.com/26/0323/zbf154447.html

[25] Figure Exceeds $1B in Series C Funding at $39B Post-Money … https://www.figure.ai/news/series-c

[26] Robotics Funding Crests Higher As Figure Lands Another $1B https://news.crunchbase.com/robotics/ai-funding-high-figure-raise-data/

[27] Figure AI: Funding, Team & Investors | Startup Intros https://startupintros.com/orgs/figure-ai

[28] 100+ Figure Ai Statistics: 2026 Verified Report - WifiTalents https://wifitalents.com/figure-ai-statistics/

[29] Sanctuary Cognitive Systems Closes C$75.5 Million (US$58.5 Million) Series A Funding, Accelerating its Mission to Create the World's First Human-Like … https://www.sanctuary.ai/blog/sanctuary-ai-closes-75-million-series-a-funding

[30] 为人形机器人穿上“新衣” 这家上市公司3亿元投向傅利叶 - 财联社 https://www.cls.cn/detail/2042476

[31] 1X Technologies - Wikipedia https://en.wikipedia.org/wiki/1X_Technologies

[32] Sanctuary AI Announces Strategic Financing From BDC Capital and InBC https://www.sanctuary.ai/blog/sanctuary-ai-announces-strategic-financing-from-bdc-capital-and-inbc

[33] Agility is reportedly raising $400M https://www.linkedin.com/pulse/agility-reportedly-raising-400m-brian-heater-io9ne

[34] 2026 Funding Rounds & List of Investors - Unitree - Tracxn https://tracxn.com/d/companies/unitree/__o1e8b3ZlyUCcjIECfbM9csfhnJyv1_fOku8o_K8gCYg/funding-and-investors

[35] Unitree closes Series B round for quadruped robots https://www.therobotreport.com/unitree-closes-series-b-round-for-quadruped-robots/

[36] 净利3亿，估值420亿！宇树科技冲刺IPO，王兴兴持股23.82% https://www.stcn.com/article/detail/3735182.html

[37] 宇树科技股份有限公司首次公开发行股票并在科创板上市招股说明书 https://static.sse.com.cn/stock/disclosure/announcement/c/202603/002178_20260320_QY8F.pdf

[38] 1X Secures $100M in Series B Funding https://www.1x.tech/discover/1x-secures-100m-in-series-b-funding

[39] 宇树科技IPO过会或成万亿赛道估值标杆 https://cn.wicinternet.org/2026-06/02/content_38807801.htm

[40] Sanctuary Cognitive Systems closes $58.5 million funding round https://www.therobotreport.com/sanctuary-cognitive-systems-closes-58-5-million-funding-round/

[41] Humanoid Robot - 2026 Market & Investments Trends - Tracxn https://tracxn.com/d/trending-business-models/startups-in-humanoid-robot/__XaLjGJXRCO_tCHXYL7TDcFDV2Kbfu3MNQXSVaa4xkas

[42] Interactive imitation learning for dexterous robotic manipulation https://pmc.ncbi.nlm.nih.gov/articles/PMC12757213/

[43] A Comprehensive Survey on Embodied Intelligence https://www.sciopen.com/article/10.26599/AIR.2024.9150042

[44] Robot learning in the era of foundation models: a survey https://dl.acm.org/doi/10.1016/j.neucom.2025.129963

[45] Embodied AI with Foundation Models for Mobile Service Robots https://www.mdpi.com/2218-6581/15/3/55

[46] BaiShuanghao/Awesome-Robotics-Manipulation https://github.com/BaiShuanghao/Awesome-Robotics-Manipulation

[47] Embodied large language models enable robots to complete ... https://www.nature.com/articles/s42256-025-01005-x

[48] Embodied AI: From LLMs to World Models https://mn.cs.tsinghua.edu.cn/xinwang/PDF/papers/2025_Embodied%20AI%20from%20LLMs%20to%20World%20Models.pdf

[49] A Survey on Vision-Language-Action Models for Embodied AI https://arxiv.org/html/2405.14093v5

[50] A SURVEY OF EMBODIED ARTIFICIAL INTELLIGENCE DATA ... https://airs.cuhk.edu.cn/sites/default/files/2025-06/Survey_Arxiv.pdf

[51] A Survey of Embodied World Models https://www.preprints.org/manuscript/202604.0928

[52] OpenMOSS/Awesome-WAM: A curated, continuously ... https://github.com/OpenMOSS/Awesome-WAM

[53] PhysWM - Learning from Causal Physical World Models https://robotik.dfki-bremen.de/en/research/projects/physwm

[54] Tool Use, Agents, and the Voyager Paper https://towardsdatascience.com/tool-use-agents-and-the-voyager-paper-5a0e548f8b38/

[55] Towards Embodied Agentic AI: Review and Classification of LLM-based Agents https://digitalcollection.zhaw.ch/server/api/core/bitstreams/b33061ea-cf82-43ca-9946-5c47f21c02f5/content

[56] Embodied Agent Interface: Benchmarking LLMs for ... https://neurips.cc/virtual/2024/poster/97552

[57] 1X Business Breakdown & Founding Story - Contrary Research https://research.contrary.com/company/1x

[58] Tesla Reorients From Premium EVs To Optimus Robots And xAI … https://finance.yahoo.com/news/tesla-reorients-premium-evs-optimus-061806827.html

[59] State of Robotics 2026 Report: $38B Market, 12 Humanoids, VLA … https://www.roboticscenter.ai/state-of-robotics-2026

[60] The global market for humanoid robots could reach $38 billion by 2035 https://www.goldmansachs.com/insights/articles/the-global-market-for-robots-could-reach-38-billion-by-2035

[61] 人形机器人公司傅利叶成估值80亿元的“独角兽” https://m.mp.oeeee.com/a/BAAFRD0000202505261089790.html

[62] 从傅利叶的战略升级，看具身智能的风向变化 - AgeClub https://www.ageclub.net/article-detail/6767

[63] AGIBOT releases GO-2 foundation model for embodied AI https://www.therobotreport.com/agibot-releases-go-2-foundation-model-embodied-ai/

[64] Foundation Models in Robotics: A Comprehensive Review of ... https://arxiv.org/html/2604.15395v1
