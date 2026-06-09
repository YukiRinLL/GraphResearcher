## 引言：具身智能的概念与本报告范围

具身智能通常被视为通过为人工智能系统赋予物理身体，使其能够在真实环境中进行交互和主动探索的一种新范式，自动驾驶和人形机器人被认为是当前最重要的两个实践方向[1]。学术综述进一步强调，具身智能的核心在于在真实场景中将物理交互能力与认知计算深度融合，是实现通用人工智能（AGI）的一条重要路径[2]。从系统角度看，具身智能不再将感知、认知、行为视为割裂的模块，而是主张感知–认知–行为一体化的整体架构[2][3]。

多篇综述和技术白皮书将多模态大模型（例如视觉–语言模型）与世界模型视为当代具身智能架构中的关键组件：前者承担多模态感知、语义理解和任务分解，后者作为“embodied world model”负责环境建模与未来预测[4][5]。同时，产业与政策研究报告将具身智能视为“万亿赛道”“新质生产力”的重要组成部分，认为 2023–2024 年在人形和服务机器人方向出现了从实验室 demo 向工程样机、小规模试点与量产规划过渡的“落地元年”迹象[6]。

本报告面向关注具身智能赛道的投资人和战略规划人员，在公开信息基础上，围绕以下维度进行系统梳理：

- 技术路线：包括多模态大模型/LLM 驱动、世界模型驱动、端到端视觉–语言–动作（VLA）、分层控制架构、传统控制与强化学习增强等[3][4][5][7]。
- 代表公司与平台：重点覆盖 Tesla Optimus、Figure AI、1X、Agility Robotics、Boston Dynamics、Unitree（宇树）、优必选、傅利叶智能、小米等人形机器人企业，以及 Google/DeepMind、NVIDIA、UBTECH、家用/服务机器人与通用服务平台（如云鲸、Agibot、Boston Dynamics Spot）等[6][8][9][10]。
- 产品形态与落地场景：涵盖人形机器人、四足/轮式平台、机械臂与服务机器人在工业、物流、家用、公共服务等场景的应用进展[1][6][8][11][12]。
- 商业化路径与营收：聚焦工业和物流场景的人形与服务机器人试点与量产准备，以及已实现规模营收的代表案例[8][9][10][13]。
- 投融资与团队：在公开证据允许范围内，给出代表公司发展阶段的定性判断（当前图谱中的融资与团队信息并不完整，很多公司只有零散二手报道，本报告不做精细融资表）。
- 趋势与风险：围绕技术路线收敛与分化、安全与可信、产业化阶段与区域差异，讨论对投资与产业布局的启示[2][4][5][14][15]。

需要特别说明：公司级财务指标（精确营收、ARR、合同金额）、部分未上市公司的融资细节以及完整团队履历在公开信息中较为缺乏或统计口径不一[6][8][9][10][13][16]。本报告对相关内容仅采用“公开信息显示”“业内报道认为”等表述，并避免超出证据范围的精确数字化比较。

---

## 第一章 全球具身智能的主要技术路线

### 1.1 方法论与总体框架

#### 1.1.1 感知–认知–行为一体化与“大脑/小脑/肢体”划分

从学术视角，具身智能被定义为在真实环境中将物理交互能力与认知计算深度结合的系统，其研究应从感知–认知–行为一体化出发，而不是孤立优化单一模块[2][3]。有综述提出“大感知–认知–行为模型”（Large PCB models）的概念，作为统一感知、认知和行为的具身大模型框架，相当于具身版的端到端大模型体系[3]。

产业层面，中国信息通信研究院的人形机器人产业报告将人形机器人系统拆分为“大脑、小脑、肢体”三部分：大脑负责环境感知、行为控制和人机交互等任务级智能，小脑负责运动控制，肢体负责执行高动态运动[17]。自 2022 年起，行业从强调液压驱动和高动态运动的阶段，转向以电驱和智能化为特征的阶段，大脑部分普遍引入 AI 大模型和云边协同，成为“智能化”演进的核心[17]。

学术综述《Aligning Cyber Space with Physical World: A Comprehensive Survey on Embodied AI》进一步提出 ABC 框架，将具身 agent 分为 AI 大脑（A）、机体（B）和跨模态传感器（C），其中 AI 大脑包含具身 world model，跨模态传感器负责主动收集多模态信息增强情境感知，机体执行动作并与人类及工具交互[4][18]。这一框架与产业界的“大脑/小脑/肢体”划分在理念上高度契合：大脑/AI brain 中的大模型和世界模型承担高层认知与规划，小脑与控制模块保证动作级安全执行，而肢体/Body 与传感器形成具身交互的硬件基础[4][17][18]。

#### 1.1.2 多模态大模型、世界模型与安全可信框架

多篇综述与技术指南将多模态大模型（MLM/MLLM、VLM、VLA）和世界模型视为当代具身智能架构中的两个核心技术模块[4][5][7][19]：

- 多模态大模型（LLM/MLLM/VLM/VLA）：负责多模态感知、语义理解、任务分解和从自然语言到高层动作的映射，是高层规划和人机交互的关键[4][5][7][20][21]。
- 世界模型（World Model）：通过建立环境的内部表征并进行多步未来预测，支持物理一致的交互和基于模型的强化学习、模型预测控制等规划与控制[4][5][22]。

此外，具身 AI 的安全与可信逐渐成为独立研究方向。ACM 的安全综述提出三分式漏洞分类框架，从感知、规划和交互环节结构化分析具身系统的安全脆弱性，指出端到端 RL/IL agent 在对抗环境下容易被扰动误导，LLM/MLM 驱动的具身 agent 则面临指令注入和行为操控风险[23]。上海人工智能实验室的安全白皮书则提出 L1–L5 五级安全等级和十条可信与安全核心原则，从指令理解、环境感知、行为规划和物理交互四阶段构建 agent 中心的安全分析框架，强调需要从单组件优化转向“自我–世界–交互”闭环的系统安全工程[14][24]。

从投资与战略规划角度，这意味着未来技术路线选择不仅取决于单点性能，更需要考虑“大模型 + 世界模型”协同能力、安全鲁棒性和可能的监管约束[4][5][14][23][24]。

### 1.2 关键技术路线拆分

综合综述文献、技术指南与企业实践，可将当前具身智能的主要技术路线概括为以下几类（实际系统往往是多路线融合）：

#### 1.2.1 端到端 Vision–Language–Action（VLA）模型

针对具身任务的 VLA 模型被视为机器人领域的一类基础模型形态，通过联合建模视觉感知、语言指令和动作输出，实现端到端或半端到端的策略学习[7]。VLA 专题综述系统梳理了这类模型的核心方法、训练数据与评测基准，强调其在导航与操作任务中的代表性地位[7][19]。

Embodied-AI-Guide 等技术指南将策略设计路线归纳为多模态 Transformer、世界模型以及端到端行为克隆/强化学习等架构，并列出大量 VLA 相关项目[25][26]。Google RT-1 是早期代表：使用 Transformer 处理视觉与文本指令，直接输出控制指令，在多任务场景下实现视觉–语言–动作映射[21][27]。

代表性产业实践包括：

- Figure Helix：通用 humanoid VLA 模型，采用 S2 高层 latent planning + S1 低层控制双系统结构，在嵌入式 GPU 上板载运行，通过大量人机示教数据进行模仿学习，单一权重即可在自然语言指令下控制两台 humanoid 完成长程 manipulation 任务[28][29]。
- NVIDIA Isaac GR00T N1：面向 humanoid 的开放 VLA foundation model，采用 System 2 视觉语言模块与 System 1 Diffusion Transformer 动作模块的双系统架构，通过混合人类视频、机器人轨迹与合成数据联合训练，可在 Fourier GR-1 和 1X NEO 等机体上实现语言条件的双臂操作[30][31]。
- 1X Redwood：为 NEO 设计的 vision–language transformer，输入包括语言嵌入、视觉 token 和本体感受信号，通过多层 transformer 与 diffusion policy 输出动作，使用真实家庭/办公室遥操作轨迹进行端到端模仿学习，支持跨 EVE/NEO 机体共享模型主体[32][33]。

这一路线正向“多机体、多任务、板载实时推理”演进，但对数据规模、长尾场景和安全性要求极高[5][7][25][32][33]。

#### 1.2.2 LLM 驱动的分层架构（高层大模型 + 低层控制）

大量学术与产业实践采用“高层大模型 + 低层传统控制或小型策略网络”的分层架构，以平衡语义能力与物理安全[3][10][20][34]：

- 学术文章提出多层级控制框架：需求级、任务级、规划级和动作级。大型自然语言模型用于任务理解与指令解析，视觉–语言或视觉–动作模型负责场景理解与高层决策，动作级执行由传统控制、优化算法或小策略网络承担[10][34][35]。
- 《基于大模型的具身智能系统综述》指出，大模型在需求/任务级承担自然语言需求理解与任务分解，在规划级作为策略或世界模型生成动作序列，动作级由较小策略网络或控制器接管，部署多采用“云端训练 + 端侧蒸馏模型实时控制”[3][36][37]。
- Agility Digit 的软件栈采用 Cognition–Skills–Control 三层结构：Cognition 层适合集成 LLM 与 VLA 模型，Skills 层通过示教学习获得技能，Control 层保证低层稳定与安全[38][39]。

企业实践：

- Tesla Optimus：产业报告认为其从 FSD 算法迁移，采用端到端 Transformer 类网络构建覆盖感知与控制的通用模型，在 Dojo 等平台上云端训练后下发机器人端执行，仍保留底层控制安全约束[40][41][42]。
- UBTECH 的 Walker 系列：使用自研 Thinker embodied AI foundation model 和 Embodied Interactive Large Model，前者提升 Walker S2 在物料处理与检测任务中的自主决策能力，后者为 Walker C 在服务场景提供多语言交互与多模态能力[9][42][43][44]。
- 部分项目通过将通用 LLM（如 ERNIE Bot）集成到 humanoid 上，实现自然语言指令下的任务执行，这类集成通常位于需求/任务级，底层控制仍由专用模块承担[45]。

这种分层架构在可解释性与安全性方面具有优势，但在长序列视频理解和物理一致执行之间仍存在挑战，需要进一步引入世界模型等模块[5][10][35]。

#### 1.2.3 世界模型与规划（World Model-driven Embodied AI）

世界模型通过学习环境内部表征并进行多步预测，使具身 agent 能进行物理一致的交互，是 model-based RL 和 MPC 等方法的基础[5][22]。《Embodied AI: From LLMs to World Models》将世界模型驱动路线与 LLM/MLLM 驱动路线并列为具身智能的两大关键驱动力[5][22]。

实践案例包括：

- Unitree UnifoLM：被描述为“Unitree Robot Unified Large Model”和“robot world model”，用于驱动 G1 在工厂执行装配任务，展示 embodied AI 模型在生产线实际应用[46][47]。
- NVIDIA GR00T N1：采用 System 2 + System 1 dual-system 架构，本质上融合世界模型式表征与动作生成，训练数据混合真实轨迹、人类视频、仿真与合成数据，提高泛化与样本效率[30][31]。

世界模型路线有望提升物理一致性和样本效率，但也增加了系统复杂度，对工程实现与调试提出更高要求[5][25]。

#### 1.2.4 传统控制基础上的 AI 增强与强化学习

不少具身平台仍在沿用传统控制与模型预测控制（MPC），并在此基础上引入强化学习和数据驱动方法[42][48][49][50]：

- Boston Dynamics Atlas：从传统 MPC 和手工策略出发，逐步引入强化学习与数据驱动方法，与研究机构合作以缩短新技能训练周期[42]。
- Agility Digit：在仓储场景中采用步态足迹规划 + MPC 的导航栈，在拥挤环境和高负载情况下保持可靠运动[48]。
- Unitree：在 Mujoco、IsaacLab 等仿真环境中使用强化学习训练控制策略，支撑其四足、轮式和人形机器人控制栈[49][50]。

这一路线对于安全关键场景尤其重要：在保持工程可靠性的前提下逐步提升“智能化”程度，是很多工业客户更愿意接受的演进路径。

---

## 第二章 按技术路线划分的代表性公司与技术路径

本章在 1.2 的基础上，从“人形机器人”和“其他具身平台”两类，提炼典型公司及其技术路径。受限于公开信息，不同公司的技术细节粒度不完全一致。

### 2.1 人形机器人方向

#### 2.1.1 Tesla Optimus：FSD 迁移的端到端大模型路线

- 技术路径：
  - 通过将汽车 FSD 的端到端 Transformer 网络迁移到人形机器人场景，构建覆盖感知和控制的通用模型[40][41][42]。
  - 使用自研 FSD 芯片与摄像头传感器，实现纯视觉感知与决策[17][40]。
- 训练与部署：
  - 在云端平台（包括 Dojo）利用汽车与机器人多模态数据进行训练，通过 OTA 更新部署至 Optimus 本体[41][51]。
- 机体与能力：
  - Optimus Gen1：电驱，约 28 自由度，展示基础行走与抓取能力[17]。
  - Gen2：更轻、更快，步速提高、行走与抓取更自然，并配备全手指触觉传感器实现精细抓取[17][52]。
- 路线特点：端到端 Transformer + 云端训练 + 电驱人形本体，是“LLM/大模型驱动分层架构”和“纯端到端”之间的一种工程实践。

#### 2.1.2 Figure AI：Helix VLA 与通用具身智能

- VLA 技术路径：
  - Helix 是 generalist humanoid VLA 模型，采用 S2 latent planning + S1 控制双系统架构，在两块嵌入式 GPU 上板载运行[28][29][30]。
  - 使用大规模人机示教数据进行模仿学习，单一权重可以在自然语言指令下控制多台 humanoid 执行未见任务，无需任务专用微调[28][29]。
- 训练与部署：
  - 采用云端大规模训练 + 端侧推理模式，利用大规模 GPU 集群训练 Helix，然后部署于 Figure 01–03 的机载算力平台[42]。
- 场景规划：
  - 短期聚焦工业装配和搬运，中期扩展家庭场景，长期目标是通用具身智能[42][53]。
- 代表意义：Figure 是“通用 humanoid VLA + 大规模模仿学习 + 云–端协同”的典型代表，也是公开技术细节较多的开创性公司之一。

#### 2.1.3 Agility Robotics Digit：三层架构与物流场景

- 软件架构：
  - Digit 的软件栈分为 Cognition–Skills–Control 三层，Cognition 层集成 AI 模型用于高层决策与语义理解，Skills 层通过示教学习获得技能，Control 层基于传统控制保障稳定与安全[38][39]。
- 训练与导航：
  - 通过遥操作采集复杂任务演示，在仿真和真实环境中联合训练[39]。
  - 在仓储场景采用步态足迹规划 + MPC 导航栈，优化步数、速度和负载下稳定性[48]。
- 商业化场景：
  - Digit 已在大仓储/物流环境执行搬运与分拣任务，被视为首批进入商业部署阶段的人形机器人之一[8][54]。
  - Salem 的 RoboFab 工厂自 2024 年起量产 Digit，支持扩展部署[9][55]。

#### 2.1.4 1X NEO：Redwood Vision–Language Transformer

- 模型架构：
  - Redwood 以 vision–language transformer + diffusion policy 结构实现端到端移动操作[32][33]。
  - 输入包括语言嵌入、视觉 token 和本体感受信号，经多层 transformer 处理后输出动作序列，并通过多个解码头适配 EVE 和 NEO 等机体[32][56]。
- 训练范式：
  - 主要基于真实家庭和办公室环境中的遥操作与自动执行轨迹进行模仿学习，加入碰手和目标位置预测等辅助任务提升表示能力[33][56]。
- 部署方式：
  - Redwood 完全在 NEO 的板载 GPU 上运行，通过外部 LLM 实现自然语言理解，两者通过接口集成[33][57][58]。

Redwood 展示了“板载 VLA + 多机体共享 + 外部 LLM 接口”的技术路径。

#### 2.1.5 Unitree：G1、UnifoLM 与 RL 路线

- 技术栈：
  - G1 被描述为通过模仿学习和强化学习驱动的 humanoid agent AI avatar，依托 UnifoLM 统一大模型作为世界模型[46]。
  - UnifoLM 被定位为 robot world model 与协同平台，支持跨机体、跨场景的策略共享[46][47]。
- 训练与应用：
  - 通过多个仿真 RL 仓库在 Mujoco/IsaacLab 等环境中大量训练策略[49][50]。
  - 在 Unitree 工厂中，UnifoLM-X1-0 embodied AI 模型驱动 G1 执行装配任务，展示 embodied AI 在生产线上的应用[47]。

#### 2.1.6 UBTECH 优必选：Walker 系列与具身 foundation model

- 技术路径：
  - Walker S1/S2 工业 humanoid 通过 Thinker embodied AI foundation model 提升物料处理与检测任务的自主能力，可自主确定码垛策略并在复杂环境中执行多步骤任务[9][59]。
  - Walker C 服务 humanoid 搭载 Embodied Interactive Large Model，具备多语言交互与多模态对话能力，将在 2025 大阪世博会中国馆担任 embodied AI 导览 humanoid[10][44]。
- 应用场景：
  - Walker S 在 Zeekr 工厂等场景作为机器人班组成员执行物料搬运与检测任务，与多台机器人协同执行复杂工艺[10][11][60]。
- 商业数据：
  - 公开信息显示，2025 年 UBTECH full-size embodied AI humanoid 收入达到 8.21 亿元，占公司总收入 41.1%，累计销售 1079 台[9]。

#### 2.1.7 傅利叶智能 Fourier：GR-1 量产 humanoid 与纯视觉方案

- 技术路径：
  - GR-1 是一款量产全尺寸 humanoid，由大语言模型驱动，可自动执行任务并进行自然语言对话[61]。
  - 在感知层面采用纯视觉方案：集成 BEV、Transformer 和 occupancy network，通过六个 RGB 摄像头构建 3D 占据栅格，实现 360° 环境理解和实时避障[61][62][63]。
- 生态合作：
  - NVIDIA GR00T N1 在 GR-1 上的部署展示了“外部 VLA foundation model + 厂商自研感知控制栈”的合作路径[30][31]。

#### 2.1.8 宇树与小米等其他厂商

- 宇树科技：
  - 从四足机器人起步，随后推出 H1、G1 等人形或小型类人产品，强调低成本、小体积和敏捷性，目标市场覆盖工厂自动化、物流和家庭服务等[64][65][66]。
- 小米与其他国内厂商：
  - 北京人形机器人创新中心报告列出小米、宇树、优必选、傅利叶、Agibot 等多家企业的人形产品或样机，标注 demo 展示年份、工程样机进度和量产计划，并划分家用服务、工业制造、物流搬运和商用服务等应用方向[8][67]。

目前公开资料对小米等企业的具身技术栈披露有限，本报告仅能给出产品层面的定性信息。

### 2.2 其他具身平台与技术主体

#### 2.2.1 Google/DeepMind：RT-1、PaLM-E 路线

- RT-1：基于大规模机器人数据训练的 VLA 模型，使用 Transformer 处理视觉与文本指令，直接输出控制指令，支持多任务操作[21][27]。
- PaLM-E：将大型语言模型 PaLM 与视觉等多模态输入结合，用于具身任务中的语义理解和规划，可与机器人控制系统集成执行复杂任务[21][68]。
- 仿真 + 真实数据：Google 在具身训练中采用仿真和真实机器人数据混合训练，提高长尾场景泛化能力[21][27]。

#### 2.2.2 NVIDIA：Isaac GR00T N1 基础模型

GR00T N1 采用 System 2 视觉语言模块和 System 1 Diffusion Transformer 动作模块的 dual-system 结构，混合使用真实轨迹、人类视频、仿真和合成数据训练，用于支持多家 humanoid 机体（如 Fourier GR-1、1X NEO）的语言条件控制[30][31]。这一路线代表“平台型具身基础模型 + 多机体生态”的技术方向。

#### 2.2.3 Boston Dynamics：Atlas 与 Spot

- Atlas：从液压版向纯电驱新 Atlas 迭代，体现从高动态液压系统向更易量产的电驱架构演进[17]。在控制上逐步引入强化学习，与传统 MPC 结合提升复杂动态技能训练效率[42]。
- Spot：四足服务平台，已在能源、公用事业、制造、矿业和公共安全等多个行业广泛部署，用于远程巡检和危险环境作业，代表“工程可靠性 + 场景拓展”的典型路径[15][69][70]。

#### 2.2.4 家用与服务机器人：云鲸等

- 云鲸智能：
  - 在扫拖一体机器人市场处于领先地位，其产品具备自动路径规划和自动集尘/换水功能，在家庭清洁场景中广泛部署[16][71]。
  - 获得腾讯、字节跳动、红杉中国和源码资本等知名机构投资，是家用服务机器人赛道的重要公司之一[16][72]。
- 服务机器人 + 机械臂：
  - IDC 报告指出，商用服务机器人搭载机械臂的组合形态正在楼宇、酒店、银行等场景实现试点，用于按电梯按钮、抓取与货架整理等具身动作任务[73][74]。

#### 2.2.5 通用服务平台与其他形态

- Agibot：从通用机器人平台出发，强调通过具身智能提升企业服务与物流机器人的感知、决策与控制能力，是“企业服务 + 具身智能”结合的案例[75][76]。
- 中国场景：服务机器人与协作机械臂在舞台演出、银行与政务大厅、工业车间、家务训练和康养场景中已有示范应用，反映出具身智能从实验室走向公共服务与工业现场的过程[12][77][78]。

---

## 第三章 产品形态、产品进度与落地场景

### 3.1 人形机器人：阶段与应用

多份产业报告与媒体综述认为，2023–2024 年大多数人形机器人处于概念机、工程样机或小批量试点阶段，仅有少数进入量产或计划量产[6][13][79]。

从产品阶段看：

- 概念机/演示：
  - 多家公司在 2023–2024 年发布人形 demo 或概念机（包括国内厂商和小米等），主要展示行走与基本操作能力[8][67]。
  - 舞台与展览演示（如大型晚会上的人形机器人表演）多为概念展示[12][77]。
- 工程样机与试点：
  - Tesla Optimus：2024 年仍以内部试点为主，计划 2025 年开始公司内部低量产[17][80][81]。
  - Figure 01/02/03：已进入工业装配与搬运试点合作阶段，但具体项目与数量信息公开有限[42][53]。
  - Agility Digit：在仓储与物流场景进行试点，被用于搬运与分拣任务，属于早期商业部署阶段[8][54]。
  - UBTECH Walker S：在比亚迪等工厂执行搬运与检测实训任务，体现工程样机与试点阶段[11][12][60]。
- 量产与规模交付：
  - Agility RoboFab：自 2024 年起量产 Digit，为多客户部署提供产能[9][55]。
  - UBTECH Walker S 系列：在 2024–2025 年实现过千台规模交付，显示人形机器人在特定工业场景达到初步规模化[9]。
  - Fourier GR-1：以量产 humanoid 形态对外发布，但具体出货量未见详细公开数据[61][62]。

整体来看，人形机器人当前主要集中在工业与物流场景的试点与早期量产，泛用家用场景部署仍较少[6][13][79]。

### 3.2 家用/服务机器人场景

- 家用清洁与基础家务：
  - 云鲸等产品在家庭清洁市场已经形成规模应用，具备自主路径规划与自动集尘/换水能力，代表具身智能在家用清洁领域的成熟应用[16][71]。
  - 行业评论认为，除清洁外，家用具身智能在家务与陪护方面整体仍处“0.1 阶段”，短期内难以形成与工业场景同量级的商业回报[18][82]。
- 楼宇/酒店/银行与公共设施：
  - IDC 报告指出，搭载机械臂的服务机器人在楼宇、酒店、银行等场景中用于按电梯按钮、抓取和货架整理等任务，已有试点和初步商业化项目[73][74]。
  - 新华网等报道展示了在银行与政务大厅中部署服务机器人接待顾客，在家务与康养场景中使用具身智能系统辅助训练和照护的案例[12][77][78]。

相较工业与物流，家用与服务场景的商业模式更分散，需求多样，短期规模化难度较大，但在特定细分领域（如清洁与康养）已出现较成熟的案例。

### 3.3 工业与物流机器人落地

多份资料确认，工业制造与物流是当前具身智能机器人商业化最活跃的领域[1][6][8][9][11][12]：

- 工厂与产线：
  - UBTECH Walker S 在 Zeekr 等工厂中作为机器人班组成员执行物料搬运和检测任务，标志着人形机器人在汽车等行业产线试点部署[10][11][60]。
  - Unitree G1 在 Unitree 工厂执行装配任务，展示 embodied AI 模型在机器人制造中的应用[47]。
  - 中国工业车间中协作机械臂与人形机器人用于辅助人工作业与危险场景作业，提高生产安全与效率[12][77][78]。
- 仓储与物流：
  - Agility Digit 在仓储与物流环境执行搬运、分拣与周转任务，结合 RoboFab 工厂量产，目标实现更大规模商业部署[8][9][54][55]。
- 巡检与安全：
  - Boston Dynamics Spot 已在能源、公用事业、制造、矿业和公共安全等行业广泛部署，用于危险环境巡检和“代替人员下井”等任务，是具身智能在巡检与安全领域成熟商业应用的代表[15][69][70]。

工业与物流场景具有刚性需求与集中的 B 端客户，对“高可靠性 + 智能化”结合的要求较高，也是人形与其他具身机器人商业化的重点方向。

---

## 第四章 商业化路径与营收进展

### 4.1 主流商业模式

综合行业报告和公开案例，当前具身智能商业模式大致包括：

- 硬件销售 + 项目交付：在工业和物流场景，常以一次性硬件销售配合项目制方案交付模式为主，如 Digit、Walker S、Spot 等[8][9][15]。
- 机器人即服务（RaaS）：部分巡检与服务机器人采用租赁或订阅模式，按使用时长、任务量或性能指标计费，减少客户一次性采购压力（具体合同结构在公开资料中尚不充分）[15][83]。
- 硬件 + 云服务/模型订阅：对于采用云端训练的大模型，如 Tesla、Figure、Google 等路线，未来可能形成“模型订阅 + 机器人终端”的收费模式，但目前公开信息仍以技术描述为主[5][21][40][41][42]。
- 基础模型平台 + 机体授权：NVIDIA GR00T N1 展示了通过开放 VLA foundation model 支撑多家机体厂商的合作模式，可能采用授权与云服务结合的商业路径[30][31]。

目前，具身智能商业模式尚在探索中，不同公司多采用混合模式，投资判断需要关注其场景适配能力与服务能力，而不仅是本体销售。

### 4.2 典型公司商业化案例（基于现有证据）

由于图谱中缺乏针对 Figure–BMW、Agility–GXO、Sanctuary–Canadian Tire/Magna、1X–ADT 等具体商业合同的直接证据，本节仅基于已收录的公开报道与数据给出具代表性的商业化案例，避免超出证据范围的配对叙述。

- Agility Robotics Digit：
  - 报道 Digit 已在大型仓储或物流环境执行搬运与分拣任务，被视为首批商业部署的人形机器人之一[8][54]。
  - RoboFab 工厂自 2024 年起量产 Digit，为扩展部署提供基础[9][55]。
- UBTECH 优必选：
  - Walker S 系列在 2024–2025 年实现过千台规模交付，full-size humanoid 收入从 2024 年的 3560 万增长到 8.21 亿元人民币，占公司总收入 41.1%，体现较强商业变现能力[9]。
  - Walker S 在 Zeekr 工厂等场景作为机器人班组成员部署，由基于 DeepSeek R1 的多模态推理模型驱动，实现复杂工业环境下的多任务智能执行[10][60]。
- Boston Dynamics Spot：
  - 已在能源、公用事业、制造、矿业和公共安全等行业形成成熟巡检部署，用于在高风险环境替代人工作业，直接带来安全和效率收益[15][69][70]。
- 云鲸智能：
  - 其扫拖一体机器人在家用清洁市场内大规模应用，获得腾讯、字节跳动、红杉中国、源码资本等机构投资，表明家用具身智能在清洁场景已具备较成熟商业价值[16][71][72]。

对于 Figure AI、Sanctuary AI、1X 等公司，现有图谱主要是技术与产品级资料，对具体营收与合同金额缺乏公开数据。本报告因此不作具体营收与订单规模推断。

### 4.3 商业化阶段判断与区域差异

综合产业报告与评论：

- 多篇资料将 2023–2024 年视为具身智能特别是人形机器人从 demo 向工程样机、小规模试点与量产规划过渡的“落地元年”[6][1][79]。
- 同时也有评论指出，整体来看具身智能仍处于“0.1 阶段”，大量项目仍以试点和示范为主，距离大规模泛用商业部署还有相当距离[18][82]。二者可以理解为“已进入试点落地阶段，但整体仍处早期探索”的不同表达。
- 区域层面，中国在政策与产业集群推动下，在人形机器人本体、应用场景和 ToB/ToG 商业项目上进展较快，但在具身大模型、仿真平台和关键零部件等基础层面与国际领先水平仍有差距[1][84]。

---

## 第五章 投融资情况与核心团队概览（基于有限公开信息）

当前图谱内关于逐家公司 2021–2024 年融资轮次、金额和团队背景的信息较为零散，主要来自部分新闻和资料条目，未形成完整的结构化表格。综合已有证据，可得出以下有限结论：

- Figure AI：
  - 维基百科条目对公司历史与产品（Figure 01–03 和 VLA 模型 Helix）有简要介绍[85]。有关 A、B、C 轮融资金额和估值的信息在图谱中未以可核查形式出现，本报告不加复述。
- UBTECH 优必选：
  - 公开报道更侧重营收与产品交付情况，例如 2025 年 full-size humanoid 收入 8.21 亿元，占总收入 41.1%[9]。关于 A、C、D 轮融资及主要投资方有零散提及，但在当前图谱中不完整。
- 云鲸智能：
  - 创业邦等报道指出，云鲸获得腾讯、字节跳动、红杉中国和源码资本等知名机构投资，是家用服务机器人领域的重要企业[16][72]。
- 其他公司（Agility Robotics、Sanctuary AI、1X、Unitree、傅利叶等）：
  - 图谱中仅残留少量总融资规模或轮次数的数据库类信息，但缺少来自公司公告或多源新闻的系统交叉验证。

在核心团队方面，除 Figure AI 维基条目对公司创始人创业背景有简要描述外，其他企业的创始人、CEO 和 CTO 的教育与职业经历未在图谱证据中系统呈现。本报告因此不对团队构成做进一步推断。

总体而言，在当前证据下，很难构建按公司 × 年份的完整融资表和团队履历。对于需要做详细财务与团队尽职调查的投资决策，建议结合公司官方披露、权威数据库和线下访谈进行补充。

---

## 第六章 综合评估与趋势判断

### 6.1 技术路线的收敛与分化

结合学术与产业资料，具身智能技术路线呈现“高层收敛、底层分化”的特征：

- 高层收敛：
  - 多模态大模型和世界模型被普遍视为具身智能“大脑”的核心组成[4][5][25][30][46]。
  - 分层架构（高层大模型/策略 + 低层传统控制/小模型）成为多数公司采纳的工程折中方案，如 Digit 的 Cognition–Skills–Control 架构、学术多层级控制框架以及 UBTECH 的 Walker 技术路线[3][10][34][38][59]。
- 底层分化：
  - 感知路线：既有纯视觉 BEV+Transformer+occupancy 网络方案（Fourier GR-1），也有传统多模态传感器融合方案（Spot 等）[62][66][69]。
  - 训练范式：行为克隆、强化学习、自监督、多任务学习以及仿真+真实数据混合训练等多种组合并存[3][25][49][50]。
  - 平台形态：人形、四足、轮式、机械臂和组合平台（服务机器人+机械臂）根据场景需求并行发展[1][6][11][15][73]。

对产业参与者而言，技术选择不再是“是否上大模型”的问题，而是如何针对目标场景，在 VLA、LLM、世界模型、传统控制和 RL 之间找到合适的组合与工程权衡。

### 6.2 商业化与资本市场风险点

综合安全与产业综述，可识别以下风险要点：

- 技术不确定性：
  - 大模型在具身场景存在长序列视频建模和幻觉问题，可能导致任务执行不稳定，尤其在高风险物理环境下[10][35]。
  - 端到端 RL/IL agent 在对抗环境下鲁棒性不足，LLM/MLM 驱动 agent 易受指令注入和行为操控攻击[23]。
- 数据与算力成本：
  - 训练大规模 VLA 与世界模型需要海量多模态数据和高算力平台（如 Dojo 等），对初创企业构成进入门槛[3][5][21][40]。
- 落地节奏：
  - 尽管 2023–2024 年出现“落地元年”的说法，但大多数人形机器人仍处样机与试点阶段，短期收入和利润贡献有限[6][13][79][18][82]。
- 安全与监管：
  - 随着具身系统自主性与物理能力提升，安全与可信的法规和标准将愈发重要，L1–L5 安全等级和十条可信原则预示未来的合规框架[14][24]。
- 区域差异：
  - 中国在具身大模型、仿真平台和关键零部件方面与国际先进水平仍有差距，需在基础层面持续投入[1][84]。

这些风险提示投资人需要警惕“估值先行、技术与应用滞后”的情形，并将安全与可靠性视作长期竞争力的重要组成部分。

### 6.3 对投资与产业布局的启示（基于公开证据的分析）

在不构成投资建议的前提下，结合当前证据可以给出若干方向性思考：

1. **关注具备完整“场景–技术–数据闭环”的主体**  
   能在工业或物流等刚需场景形成数据闭环，并具备从高层模型到底层控制全栈能力、已实现规模交付或明确工厂部署的企业（如 Digit + RoboFab、Walker S 在工厂班组中的部署、Spot 在巡检场景中的大规模应用），在中期更有可能形成可持续商业模式[8][9][11][15][47][55][60]。

2. **重视基础模型与平台生态的杠杆效应**  
   NVIDIA GR00T N1 这类开放 VLA foundation model，通过支持多机体适配，为整个生态提供通用具身智能基础设施[30][31]。对软硬件厂商而言，围绕基础模型构建生态可能成为重要战略方向。

3. **区分短期现金流场景与长期通用具身智能叙事**  
   目前已有较明确商业价值的场景包括家用清洁、巡检、安全和部分工业与物流任务，通用家用人形与“全能家务机器人”的商业化仍存在时间和技术不确定性[6][15][16][18][82]。资产配置可在具备稳定现金流的成熟场景与长期具身智能期权之间平衡。

4. **将安全与可信视作核心护城河之一**  
   具身系统带来的物理风险远高于纯软件系统。能够在 L1–L5 安全等级框架下提供系统性安全方案的企业在高风险场景（化工、矿业、公共安全）中可能具有差异化优势[14][23][24]。

5. **关注中国在具身大模型与关键部件上的追赶节奏**  
   中国在具身大模型、仿真平台、机器人本体和关键零部件上仍需持续投入，政策和产业集群建设有望缩小差距[1][84]。在这些关键环节提前布局，可能在未来全球竞争中获得战略位置。

---

## 参考文献

[1] Aligning Cyber Space with Physical World: A Comprehensive Survey on Embodied AI https://arxiv.org/html/2407.06886v8

[2] Paper List and Resource Repository for Embodied AI https://github.com/HCPLab-SYSU/Embodied_AI_Paper_List

[3] A Comprehensive Survey on Embodied Intelligence: Advancements, Challenges, and Future Perspectives https://www.sciopen.com/article/10.26599/AIR.2024.9150042

[4] Embodied AI: A Survey on the Evolution from Perceptive to … https://onlinelibrary.wiley.com/doi/full/10.1002/smb2.70003

[5] Towards Robust and Secure Embodied AI: A Survey on … https://dl.acm.org/doi/10.1145/3806048

[6] Embodied AI: From LLMs to World Models https://mn.cs.tsinghua.edu.cn/xinwang/PDF/papers/2025_Embodied%20AI%20from%20LLMs%20to%20World%20Models.pdf

[7] Toward the next frontier of embodied AI https://www.oaepublish.com/articles/ir.2025.44

[8] Towards Safe and Trustworthy Embodied AI: Foundations, Status, and Prospects https://openreview.net/pdf/a3b0eb5349f3c0dd92e21b43b04037add70c669a.pdf

[9] 具身智能发展报告 https://www.caict.ac.cn/kxyj/qwfb/bps/202408/P020240830312499650772.pdf

[10] 具身智能：万亿赛道，落地元年 https://pdf.dfcfw.com/pdf/H3_AP202503101644227280_1.pdf

[11] 具身智能：赋能中国及全球企业价值的新质生产力——从愿景到落地 https://www.infosys.com/cn/global-sourcing/embodied-ai-new-productivity-force.pdf

[12] 2025年具身智能机器人发展趋势 https://my.idc.com/getdoc.jsp?containerId=prCHC53054525

[13] 具身智能发展趋势与展望 Embodied Intelligence https://www.engineering.org.cn/sscae/CN/PDF/10.15302/J-SSCAE-2025.07.019

[14] 具身智能发展报告 https://x-humanoid.com/storage/website/2025/01-14/6785fd2145c36-1-27438.pdf

[15] 具身智能即将为通用机器人补全最后一块拼图 https://www.agibot.com/article/188/detail/7.html

[16] 从机器人到具身智能：人工智能的“具身化”演进 https://www.bjrd.gov.cn/fwhd/bjrdzz/2025n/bjrdzz202509q/yjyts202509/202509/t20250930_4214986.html

[17] 具身智能：从场景落地到产业崛起 https://www.news.cn/tech/20260309/f25f9688d2e2470c8654ee4c2d107063/c.html

[18] Prospects and technology of embodied intelligent humanoid robots https://www.sciengine.com/doi/10.1360/SSI-2024-0350

[19] 人形机器人产业发展研究报告（2024 年） https://www.film-expo.com/content/dam/sitebuilder/rxch/filmexpo/2025/2/14/%E4%B8%AD%E5%9B%BD%E4%BF%A1%E9%80%9A%E9%99%A2-%E4%BA%BA%E5%BD%A2%E6%9C%BA%E5%99%A8%E4%BA%BA%E4%BA%A7%E4%B8%9A%E5%8F%91%E5%B1%95%E7%A0%94%E7%A9%B6%E6%8A%A5%E5%91%8A.pdf.coredownload.394992768.pdf

[20] 中美机器人发展深度分析报告（初稿） https://file.jgvogel.cn/125/upload/resources/file/616028.pdf

[21] 基于大模型的具身智能系统综述 https://www.aas.net.cn/cn/article/doi/10.16383/j.aas.c240542?viewType=HTML

[22] 具身智能技术指南 Embodied-AI-Guide https://github.com/tianxingchen/Embodied-AI-Guide

[23] 2024具身智能创新应用案例重磅发布，引领千行百业智能变革 https://m.36kr.com/p/2962489137991689

[24] 启明星 | 6家启明创投投资企业入选36氪2024具身智能创新应用案例 https://www.qimingvc.com/cn/news/%E5%90%AF%E6%98%8E%E6%98%9F-6%E5%AE%B6%E5%90%AF%E6%98%8E%E5%88%9B%E6%8A%95%E6%8A%95%E8%B5%84%E4%BC%81%E4%B8%9A%E5%85%A5%E9%80%8936%E6%B0%AA2024%E5%85%B7%E8%BA%AB%E6%99%BA%E8%83%BD%E5%88%9B%E6%96%B0%E5%BA%94%E7%94%A8%E6%A1%88%E4%BE%8B

[25] 2025第一“融” ▏具身智能赛道喜迎“开门红” 智平方宣布完成Pre-A轮融资 https://ai2robotics.com/2025%E7%AC%AC%E4%B8%80%E8%9E%8D-%E5%85%B7%E8%BA%AB%E6%99%BA%E8%83%BD%E8%B5%9B%E9%81%93%E5%96%9C%E8%BF%8E%E5%BC%80%E9%97%A8%E7%BA%A2-%E6%99%BA%E5%B9%B3

[26] 2025 具身智能赛道投资策略报告 https://www.monadventures.com/reports/13

[27] 人形机器人企业投融资法律报告（上）：行业发展与融资概况 https://www.zhonglun.com/research/articles/53371.html

[28] 具身智能商业化落地提速，企业建言从“独角戏”走向“生态共建” https://www.21jingji.com/article/20250518/herald/0d12923d4336f23e2130f442ac5e645c.html

[29] 2025商用具身智能白皮书 https://pdf.dfcfw.com/pdf/H3_AP202512031793353788_1.pdf?1764833841000.pdf

[30] 2025具身智能行业发展研究报告——具身智能技术发展与行业应用简析 https://download.s21i.co99.net/28254755/0/0/ABUIABA9GAAgmcKqvQYomLfimwU.pdf?f=2025%E5%85%B7%E8%BA%AB%E6%99%BA%E8%83%BD%E8%A1%8C%E4%B8%9A%E5%8F%91%E5%B1%95%E7%A0%94%E7%A9%B6%E6%8A%A5%E5%91%8A%E5%85%B7%E8%BA%AB%E6%99%BA%E8%83%BD%E6%8A%80%E6%9C%AF%E5%8F%91%E5%B1%95%E4%B8%8E%E8%A1%8C%E4%B8%9A%E5%BA%94%E7%94%A8%E7%AE%80%E6%9E%90.pdf&v=1739235609

[31] 具身智能机器人商业化驶入“快车道” https://cn.wicinternet.org/2025-09/10/content_38277398.htm

[32] 今年最火赛道“具身智能机器人”：半年22起融资单笔超10亿 https://www.ebrun.com/20240816/556867.shtml

[33] AI & Robotics | Tesla https://www.tesla.com/AI

[34] Tesla, Inc. DEF 14A https://ir.tesla.com/_flysystem/s3/sec/000110465924051405/tm2326076d20_defa14a-gen.pdf

[35] Tesla to have humanoid robots for internal use next year, Musk says https://www.reuters.com/business/autos-transportation/tesla-have-humanoid-robots-internal-use-next-year-musk-says-2024-07-22/

[36] A Retrospective on Uses of Boston Dynamics’ Spot Robot https://bostondynamics.com/blog/retrospective-on-boston-dynamics-spot-robot-uses/

[37] Digit is first humanoid deployed in a commercial application https://www.therobotreport.com/rbr50-company-2025/digit-is-first-humanoid-deployed-in-a-commercial-application/

[38] How Agility Robotics factory in Salem is building the robot revolution with Digit https://www.statesmanjournal.com/story/news/local/2025/09/12/salem-oregon-agility-robotics-warehouse-labor-shortage/85629748007/

[39] 国内80+人形机器人创企，商业化进展为零！！！ https://hub.baai.ac.cn/view/40996

[40] 中美人形机器人落地进展大比拼 https://m.thepaper.cn/newsDetail_forward_28197729

[41] 李泽湘爱徒干成行业第三，腾讯、红杉纷纷押注 https://m.cyzone.cn/article/784980

[42] 马斯克看中的具身智能，最多走到了0.1？ https://m.36kr.com/p/2629330051629315

[43] The Chinese Humanoid Robot AI Market - Investor Opportunities https://www.china-briefing.com/news/chinese-humanoid-robot-market-opportunities/

[44] GR00T N1: An Open Foundation Model for Generalist Humanoid Robots https://d1qx31qr3h6wln.cloudfront.net/publications/GR00T%20N1%20Whitepaper.pdf

[45] 2025 Annual Review: Embodied Intelligence Industry - From Pioneering Debut to Rational Progression https://eu.36kr.com/en/p/3615952634507783

[46] Helix: A Vision-Language-Action Model for Generalist Humanoid Control https://www.figure.ai/news/helix

[47] Helix | Figure https://www.figure.ai/helix

[48] Figure AI - Wikipedia https://en.wikipedia.org/wiki/Figure_AI

[49] Redwood AI | 1X https://www.1x.tech/discover/redwood-ai

[50] 1X NEO Robot Gains Autonomy with Redwood AI https://qviro.com/blog/1x-neo-redwood-ai

[51] Digit's Next Steps https://www.agilityrobotics.com/content/digits-next-steps

[52] 1X’s NEO humanoid gains autonomy with new Redwood AI model https://www.therobotreport.com/1xs-neo-humanoid-gains-autonomy-with-new-redwood-ai-model

[53] Unitree G1（Unitree Technology introduced the humanoid agent robot in 2024.） https://baike.baidu.com/en/item/Unitree%20G1/1512074

[54] Unitree Robotics · GitHub https://github.com/unitreerobotics

[55] UBTECH Humanoid Revenue Surges in 2025 Results https://humanoid.guide/ubtech-humanoid-revenue-surges-in-2025-results/

[56] Embodied AI: China's Big Bet on Smart Robots https://carnegieendowment.org/research/2025/11/embodied-ai-china-smart-robots

[57] UBTECH and Baidu have partnered to integrate large AI models into ... https://www.reddit.com/r/singularity/comments/1bup346/ubtech_and_baidu_have_partnered_to_integrate/

[58] Fourier GR-1 https://www.fftai.com/products-gr1

[59] NVIDIA Isaac GR00T N1: An Open Foundation Model for Humanoid Robots https://research.nvidia.com/publication/2025-03_nvidia-isaac-gr00t-n1-open-foundation-model-humanoid-robots

[60] UBTech surges in leaps and bounds as humanoid robot sales jump 23-fold https://www.scmp.com/tech/article/3348635/ubtech-surges-leaps-and-bounds-humanoid-robot-sales-jump-23-fold

[61] Humanoid Robots 2026: Tesla Optimus, Figure 02 & NVIDIA Isaac Status https://www.meta-intelligence.tech/en/insight-physical-ai

[62] Optimus (Tesla Bot) - ROBOTS: Your Guide to the World of Robotics https://robotsguide.com/robots/optimus

[63] CyberOne - Discover - Xiaomi Global Home https://www.mi.com/global/discover/article?id=2754

[64] Xiaomi CyberOne - independent comparison | The Robot Group https://www.therobotgroup.co.uk/brand/xiaomi

[65] Xiaomi CyberOne Review 2026: Full Specs, Pros & Cons https://blog.robozaps.com/b/xiaomi-cyberone-review

[66] A Survey on Vision-Language-Action Models for Embodied AI https://arxiv.org/html/2405.14093v6

[67] Embodied AI and Humanoid Robot Market Research 2024-2025: Product Technology Outlook and Supply Chain Analysis http://www.researchinchina.com/Htmls/Report/2025/77069.html

[68] Figure announces commercial agreement with BMW Manufacturing to bring general purpose robots into automotive production https://www.prnewswire.com/news-releases/figure-announces-commercial-agreement-with-bmw-manufacturing-to-bring-general-purpose-robots-into-automotive-production-302036263.html

[69] Figure 03 at BMW Spartanburg: 30,000+ Vehicle Humanoid Deployment Case Study Lessons https://ifactoryapp.com/industries/automotive-manufacturing/figure-03-bmw-spartanburg-case-study-humanoid

[70] NEWS: Figure + BMW Manufacturing Co., LLC … https://www.linkedin.com/posts/brettadcock_news-figure-bmw-manufacturing-co-llc-activity-7213582448675160064--YSz

[71] GXO signs industry-first multi-year agreement with Agility Robotics https://gxo.com/it/news_article/gxo-signs-industry-first-multi-year-agreement-with-agility-robotics

[72] Agility Robotics, GXO sign multi-year humanoid deployment agreement https://www.robotics247.com/article/agility_robotics_gxo_sign_multi_year_humanoid_deployment_agreement

[73] How Does Agility Robotics Company Operate? https://businessmodelcanvastemplate.com/blogs/how-it-works/agility-robotics-how-it-works

[74] Sanctuary AI Deploys First Humanoid General-Purpose Robot Commercially https://www.sanctuary.ai/blog/sanctuary-ai-deploys-first-humanoid-general-purpose-robot-commercially

[75] Sanctuary AI Deploys First Humanoid General-Purpose Robot Commercially https://www.evokinnovations.com/post/sanctuary-ai-deploys-first-humanoid-general-purpose-robot

[76] InBC Invests in Robotics Company Sanctuary AI https://inbcinvestment.com/inbc-invests-robotics-company-sanctuary-ai

[77] 1X Technologies: Competitive Response https://robotics.press/news/1x-technologies-competitive-response/

[78] 1X | Home Robots https://www.1x.tech/

[79] 1X Technologies https://en.wikipedia.org/wiki/1X_Technologies

[80] Agility and AI https://www.agilityrobotics.com/content/agility-and-ai

[81] Just Another Outdoor Adventure for Digit Thanks To Full-Stack Autonomy https://www.agilityrobotics.com/content/just-another-outdoor-adventure-for-digit-thanks-to-full-stack-autonomy

[82] Sanctuary AI Successfully Deploys Human-Like Intelligence Robots in Commercial Partnership with Canadian Tire Corporation https://www.impactlab.com/2023/05/31/sanctuary-ai-successfully-deploys-human-like-intelligence-robots-in-commercial-partnership-with-canadian-tire-corporation

[83] UBTECH ROBOTICS CORP LTD – ANNUAL RESULTS ANNOUNCEMENT FOR THE YEAR ENDED DECEMBER 31, 2024 https://owebsite-cdn.ubtrobot.com/resources/file/2025/04/04/662025667334213.pdf

[84] What Are the Growth Strategy and Future Prospects of UBTech Robotics? https://businessmodelcanvastemplate.com/blogs/growth-strategy/ubtech-robotics-growth-strategy

[85] Unitree G1 - ROBOTS: Your Guide to the World of Robotics https://robotsguide.com/robots/unitree-g1
