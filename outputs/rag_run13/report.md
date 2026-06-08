# 全球具身智能技术路线与代表性公司研究报告

## 一、引言：具身智能与人形机器人的崛起

具身智能（Embodied Intelligence / Embodied AI）通常指具备物理形态、能够通过传感器与执行器在真实环境中感知、决策和行动的智能体，包括人形机器人、四足/轮式移动机器人等形态。[1][2][3] 近年的综述指出，随着大规模预训练模型、强化学习和世界模型等技术发展，具身智能逐渐从虚拟仿真环境扩展到真实世界多模态交互和复杂任务执行，被视为“下一代 AI”重要方向之一。[1][2][3][4][5]

从市场侧看，多家研究机构预计，具身智能及相关机器人市场在 2020–2025/2026 年间进入高增长阶段，驱动因素包括：大模型带来的通用决策能力、传感器与算力成本下降、制造业与物流业对柔性自动化的需求提升，以及各国在“新质生产力”“先进制造”等政策上的持续投入。[6][7][8][9][10] 2024–2025 年的人形机器人专题研究进一步指出，人形机器人有望在制造、物流、安防、服务等场景中补充甚至部分替代传统工业机器人和专业移动机器人，成为具身智能商业化的标志性载体。[11][12][13][14][10][15]

本报告以 2020–2026 年为大致时间窗口，重点关注 2023–2025 年间具身智能尤其是人形机器人方向的技术路线演进与产业化进展，结合学术综述与产业研究，对以下问题进行系统梳理：

1. 具身智能/人形机器人在技术路径上的主流分类，包括端到端大模型控制、模块化感知‑规划‑控制、云端大模型+边缘执行、仿人 vs 专用形态等。[1][2][3][6][7][8][9][11][12][13][14][10][15]
2. 各技术路线下代表公司的技术方案、产品形态与商业化进度，涵盖 Figure AI、Tesla Optimus、Google DeepMind RT 系列、1X、Agility、Boston Dynamics、优必选、宇树等。[16][17][18][19][20][21][22][23][24][25][26][27][28][29][30][31][32][11][12][13][14][33][34][35][36][37][38][39][40][41][42][43][44][45][46][47][10][15]
3. 全球具身智能代表公司的融资规模、估值区间、主要投资者，以及人形机器人相关 ETF 和赛道热度。[48][49][50][51][52][53][54][55][56][57][58][59][60][61][62][63][64][65][66][67][68][69]
4. 关键企业的团队与人才结构特征，以及不同技术路线背后的人才来源差异。[28][32][33][34][37][41][42][44][45]

本报告所使用的数据与案例均来自公开文献、公司发布与第三方研究，部分信息（尤其是估值、长期出货计划等）在不同来源之间存在差异或尚未完全披露。[48][49][50][55][57][58][59][61][68][10][15] 因此，报告中的数值多以“约”“区间”“公开披露”方式呈现，不对未被公开的数据作推断，并在结尾章节说明研究的局限与后续方向。

---

## 二、技术路线总览：从大模型到形态设计

### 2.1 技术范式：从模块化到大模型驱动

多篇具身智能与人形机器人综述将当前技术路径概括为两大范式：一是传统的模块化感知‑规划‑控制架构，二是以大模型为核心的端到端或半端到端策略学习与决策架构。[1][2][3][4][5] 

1. **模块化感知‑规划‑控制**  
   系统被拆分为感知（视觉、力觉、位置等）、状态估计与建图、任务/运动规划、控制与执行等模块，每个子模块分别设计与优化，再通过接口集成到完整系统中。[1][3][4] 这种方案在工业机器人和传统移动机器人中已高度成熟，具备确定性强、安全可验证等优势。[12][13][47]

2. **大模型驱动的端到端与决策层**  
   大规模预训练模型（包括视觉‑语言模型、世界模型和决策模型）正在向具身智能渗透，主要路径包括：视觉‑语言‑动作（Vision‑Language‑Action，VLA）模型直接从感知到动作的端到端控制；大模型作为高层策略或“决策大脑”，下接传统运动与力控模块；以及在云端通过大模型进行规划，再下发到边缘侧执行。[2][3][70][31] 这类方案强调数据驱动的泛化能力和跨任务迁移，但也带来安全性与可解释性的新挑战。[1][2][3]

从应用视角，市场研究机构与行业报告将具身智能技术发展描述为“从专用任务算法走向通用大模型+数据闭环”的过程，即通过大模型统一感知、理解与决策，同时在执行层仍依赖成熟的运动控制与本体技术。[6][7][8][9][11][12][13][14][10][15]

### 2.2 端到端大模型控制路线

端到端路线的典型特征是通过单一或少量大模型，将多模态感知（视觉、语言等）映射到机器人动作序列，弱化传统的手工特征与模块化任务规划。[2][3][70][20][21][22][23][24][31] 

Google DeepMind 的 RT 系列通过 Transformer 架构学习从传感输入到控制输出的映射，在多机器人和多任务数据上进行预训练以提升泛化能力。[20][21][22][23][24] Figure 的 Helix VLA 模型和 Project Go‑Big 提出面向人形机器人的互联网规模预训练与端到端控制路径，将视觉、语言与动作统一在一个模型框架中。[16][17][18] Tesla 在 Optimus 项目中强调通过大规模视频和传感数据训练端到端神经网络，实现“video in, controls out”的控制方式。[19][71][72]

该路线的优势包括：通过数据规模驱动复杂技能和跨场景泛化，降低针对每个细分场景单独开发算法的成本，并更易与云端大模型和知识库集成，使机器人具备语言理解与世界知识推理能力。[1][2][3][20][21][22][23][24][31] 主要挑战在于对数据与算力的高需求，以及在工业场景中如何验证安全性和鲁棒性。[1][2][3][7][8]

### 2.3 模块化感知‑规划‑控制与 “Large Behavior Models”

在工业机器人和移动机器人领域，模块化感知‑规划‑控制仍是主流范式，尤其在高节拍、高安全要求的生产场景中。[12][13][47] 

Boston Dynamics 在 Atlas 以及其他产品中长期采用精确的动力学建模、感知模块和高带宽控制器，以实现复杂动态行为，并在此基础上提出“Large Behavior Models”概念，通过数据驱动方法在保持底层物理可控性的前提下学习高层行为生成。[44][45][46]

中国的人形机器人和服务机器人企业（如优必选、宇树等）在公开资料中强调自身在伺服驱动器、减速器、运动控制算法等模块化技术上的积累，同时逐步引入 AI 算法增强感知与决策，例如在导航、视觉识别和人机交互方面利用深度学习和大模型能力。[11][12][13][14][33][34][35][36][37][38][39][40][41][42][43][10][15]

这一路线结合了传统工业控制的确定性与大模型的学习能力：大模型主要作用于感知理解和任务层规划，而底层运动与安全控制仍由经过验证的模块实现，有利于向工业场景平滑过渡。[1][3][12][13][14][44][45][46]

### 2.4 云端大模型 + 边缘执行

多份市场研究和产业报告提到，具身智能在算力与延迟之间往往需要云‑边协同架构：云端部署大模型用于感知融合、任务规划或策略生成，边缘端（机器人本体）执行本地闭环控制，并在网络条件波动时具备基本自主能力。[6][7][8][9][11][12][13][14][10][15] 一些人形机器人方案选择在本体搭载 GPU/专用 AI 芯片，运行较小的本地模型，同时与云端的大模型或知识库协同，以平衡实时性与智能水平。[12][13][14][10][15]

从投资和产业生态看，云‑边协同也使得大模型公司与传统机器人厂商可以通过接口合作，共同构建具身智能解决方案，而非完全由单一厂商垂直整合。[6][7][8][9][31][11][12][13][14][10][15]

### 2.5 仿人形态 vs 专用形态

形态设计上，市场与研究报告普遍将具身智能机器人划分为仿人形态（bipedal humanoids）和专用形态（包括四足、轮式、轮腿混合等），两者各有优势与适用场景。[1][3][6][7][8][9][11][12][13][14][40][44][10][15]

- **仿人形态**：以 Figure、Tesla Optimus、1X NEO、Agility Digit、优必选 Walker、宇树 H1 等为代表，强调与人类环境高度兼容，可在现有工厂、仓库和办公空间中直接使用，无需大规模改造基础设施。[16][17][18][19][25][26][27][28][29][30][31][32][11][12][13][14][33][34][35][36][37][38][39][40][41][42][43][10][15]

- **专用形态**：包括 Boston Dynamics 早期的四足机器人、宇树的四足系列、轮式与轮腿机器人等，在特定场景（如复杂地形巡检、安防、户外任务等）具备更高的效率或稳定性。[40][41][42][44][45][46][47]

随着大模型与通用控制策略的发展，有研究与企业探索在统一的决策模型下支持多种本体形态，即通过抽象动作空间与多机器人数据训练，使单一决策模型适应不同形态机器人。[2][3][5][70][20][21][22][23][24][31] 但在工程实践上，仿人和专用形态在机械结构、成本与可靠性要求上仍存在显著差异，短中期内预计将长期并存。[1][3][6][7][8][9][11][12][13][14][40][44][10][15]

---

## 三、端到端大模型控制路线：Figure、Tesla、Google、1X 与 Agility

### 3.1 Figure：Helix VLA 与 Project Go‑Big

Figure 提出以互联网规模数据训练人形机器人决策模型的路线。Project Go‑Big 宣称通过“Internet‑Scale Humanoid Pretraining and Control”构建统一的控制与感知模型，使人形机器人能够在多场景中执行复杂任务。[16] Figure 发布的 Helix 模型被定义为 Vision‑Language‑Action（VLA）模型，通过视觉和语言输入生成动作输出，旨在让人形机器人在开放环境中具备理解任务指令与环境状态，并据此规划与执行动作的能力。[17][18]

在硬件形态上，Figure 03 被定位为面向工业与服务场景的人形机器人平台，用于在工厂等环境中承担搬运、拣选等重复性工作。[18] 产品目前仍处于原型与试点阶段，重点通过与大模型公司和工业客户合作，验证 VLA 控制在实际生产场景中的可行性与安全性。[16][17][18]

Figure 的技术路径主要特点包括：以 VLA 模型为核心，将视觉、语言与动作统一建模；使用互联网与机器人数据进行大规模预训练，并通过实际机器人执行数据进行微调；在工程上与传统运动控制和安全系统结合，以保证工业场景可用性。[16][17][18]

### 3.2 Tesla Optimus：端到端神经网络与 “video in, controls out”

Tesla 在 AI & Robotics 页面中将 Optimus 描述为面向工厂和未来家庭的通用人形机器人，强调利用在自动驾驶领域积累的感知、规划与控制技术，将“AI 大脑”与车辆共享平台技术延伸至人形机器人。[19] 社区与媒体报道提到，Optimus 的神经网络训练采用“video in, controls out”模式，即通过从视频到控制信号的端到端学习，实现自主物体分类、抓取与排序等任务。[71]

媒体展示了 Optimus 进行瑜伽动作和人机互动的画面，表明其在控制与平衡方面已经具备一定能力。[72] 不过，公开资料仍主要为演示和公司介绍，关于其在工厂内大规模部署的数量和工位类型尚缺乏细致披露，更多停留在试点和内部验证阶段。[19][71][72]

技术路线方面，Tesla 将自动驾驶中的感知与规划网络迁移到人形机器人，并结合其在电机、减速器与电池等硬件平台的经验，实现整机一体化设计。[19][64] 媒体报道还提到，Tesla 计划在 AI 与机器人方向投入数百亿美元级别资金，以支撑 Optimus 及相关项目发展。[62][63][64]

### 3.3 Google DeepMind RT 系列：从 RT‑1 到 RT‑2 的 VLA 演进

Google/Google DeepMind 在 RT 系列中系统探索了端到端 Transformer 控制路线。RT‑1 被描述为面向真实世界控制的“Robotics Transformer”，通过在大规模机器人数据集上训练，将视觉和任务指令映射到低层动作序列，实现跨任务、跨环境的泛化。[20][21] RT‑1 利用多机器人、多任务数据构建统一策略，在厨房整理、物体抓取等任务中展现出一定的零样本/少样本泛化能力。[20][21]

RT‑2 进一步被定义为“Vision‑Language‑Action”模型，能够将网络和文本知识转移到机器人控制中。[22][23][24] 官方介绍强调，RT‑2 在训练中结合网络规模的视觉‑语言数据与机器人交互数据，使机器人能够理解和执行更抽象的任务描述，例如根据文本指令选择合适对象并执行动作。[22][23][24]

RT 系列的技术特点包括：使用 Transformer 结构统一处理感知输入和动作输出；通过多源数据预训练并在机器人数据上微调，实现从网络知识到物理世界行为的迁移；将 VLA 模型作为上层策略，与机器人底层控制模块结合，而非完全替代传统控制。[20][21][22][23][24]

虽然 RT 系列主要仍处于研究与实验阶段，但其为端到端具身智能提供了标准化框架参考，推动更多企业采用类似 VLA 模型进行控制。[2][3][70][20][21][22][23][24][31]

### 3.4 1X：Redwood AI 与 NEO 的云‑边协同

1X 专注于人形机器人及其 AI 控制平台。Redwood AI 被描述为面向身体控制与认知的统一平台，旨在让机器人在家庭、企业和公共空间执行多种任务。[25][26] Redwood AI 提供感知、规划和控制模块，并通过云端服务实现持续学习与能力更新，同时支持在不同机器人形态（如 NEO 和 EVE）上的部署。[25][26]

Redwood AI Mobility 针对移动和导航能力进行优化，使机器人在动态环境中进行路径规划与避障，并在云端进行模型更新与策略优化。[26] 行业报道指出，1X 的 NEO 人形机器人通过 Redwood AI 获得更高自主性，能够在仓储与安防等场景中执行巡逻和简单操作任务。[27][28]

1X 已宣布在加利福尼亚设施开启 NEO 的生产，并计划面向企业客户提供服务，表明其正在从原型向小批量量产和商业部署过渡。[54] 公司在 2024 年前后完成约 1 亿美元融资，由多家机构（包括 OpenAI 参与的投资方）支持，后续还传出软银考虑主导新一轮 7500 万至 1 亿美元投资的消息。[51][52][53] 这些资金为其云‑边协同平台和硬件扩产提供保障。

技术上，1X 的路线可视为“云端大模型 + 边缘执行”的具身智能路径：云端 Redwood AI 负责持续学习与决策优化，本地机器人执行实时控制，并通过数据回传形成闭环。[25][26][27][28][54]

### 3.5 Agility：Digit 与基础模型时代的工业具身智能

Agility Robotics 是工业人形机器人领域的重要企业，其官网将 Digit 描述为面向仓储与制造场景的“Industrial Humanoid Automation”平台，目标是在现有设施中执行搬运、分拣和物料搬移等任务，强调与人类环境兼容。[29]

Agility 与 NVIDIA 的合作公告指出，双方将在基础模型（foundation models）与仿真平台上合作，利用大规模仿真和 AI 模型提升 Digit 的感知与决策能力。[30] 行业文章将其视为“基础模型时代机器人”的代表之一，认为其路线在于将基础模型与工业级硬件和安全标准结合，实现可规模化部署的具身智能系统。[31] 公司分析报告显示，Agility 重点瞄准物流与制造中的体力劳动岗位，通过人与机器人协作提升效率，当前处于与多家头部企业合作试点和扩展阶段。[32]

总体来看，Agility 的技术路径兼具端到端大模型和模块化控制特征：一方面利用基础模型提升感知与任务规划能力，另一方面在执行层维持工业级可靠性和安全机制。[29][30][31][32]

### 3.6 小结：端到端路线的共性与差异

端到端大模型控制路线的代表公司在技术与商业化上呈现若干共性：

- **以 VLA/基础模型为核心**：Figure 的 Helix、Google 的 RT‑2、1X 的 Redwood AI、Agility 与 NVIDIA 的合作均通过统一模型处理视觉、语言与动作，实现跨任务泛化与能力复用。[16][17][20][21][22][23][24][25][26][27][29][30][31][32]

- **强调数据闭环与云‑边协同**：Tesla 利用其在车辆上的数据优势，1X 通过 Redwood AI 云平台持续更新模型，Figure 和 Agility 依托产业合作伙伴获取真实场景数据。[16][19][71][25][26][27][28][29][30][31][32][54]

- **产品多处于原型到小批量试点阶段**：Figure、Tesla Optimus、1X NEO、Agility Digit 等均在公开资料中展示样机和场景演示，并在仓储、制造等场景启动试点，但大规模量产和广泛部署仍在推进之中。[18][19][71][72][27][28][29][30][32][54]

在差异方面，Tesla 更注重自有生态闭环与整车制造能力，Figure 强调互联网规模预训练与 VLA 模型，Google DeepMind 偏向研究与平台化框架；1X 和 Agility 在商业模式上更面向企业服务与订阅型收入，结合云端 AI 平台提供持续服务。[16][17][18][19][20][21][22][23][24][25][26][27][28][29][30][31][32][51][52][53][54]

---

## 四、模块化感知‑规划‑控制路线及传统机器人厂商升级

### 4.1 Boston Dynamics：从精确控制到 Large Behavior Models

Boston Dynamics 以高度动态的人形与四足机器人著称。Atlas 产品页面展示了其在复杂地形和高动态任务中的能力，包括跑跳、翻越、搬运等行为。[44] “Perception and Adaptability” 内容强调利用多种传感器和感知算法，使机器人能够感知环境并适应不同任务需求，依托模块化感知与高带宽控制系统。[46]

在此基础上，Boston Dynamics 提出“Large Behavior Models”概念，通过大规模数据驱动行为生成和决策，以提升机器人在未知环境中的适应性和泛化能力。[45] 目标是在确保底层动力学控制与安全性的前提下，让机器人学习更丰富的动作组合和策略，实现从精心编排的演示向数据驱动的行为库过渡。[44][45][46]

该路径体现了传统高精度控制与现代数据驱动方法的融合：底层由精确建模和控制器负责，行为层逐步交由数据驱动模型学习，从而在保持可靠性的同时提升灵活性。[44][45][46]

### 4.2 优必选：服务与教育起家的人形机器人平台

优必选（UBTECH）是中国较早布局服务机器人和人形机器人平台的企业。官方介绍将其定位为“让智能机器人走进千家万户”，产品覆盖教育、服务、安防等多个领域。[33][34] 公司资料显示，其在人形机器人、本体设计、伺服驱动、运动控制以及语音和视觉交互等方面具有全栈技术布局，并通过自研核心部件降低成本，提升系统一体化程度。[33][34][37]

在应用场景方面，优必选的人形机器人（如 Walker 系列）被用于展览展示、政务服务、科普教育等领域。官方应用场景页面列举了在展馆、企业前台、活动现场中的导览、讲解、互动等任务。[35] 报道指出，在 WAIC 2021 等活动中，Walker X 作为“全球首发”人形机器人亮相，并展示复杂步态、灵巧操作和人机交互能力。[36]

优必选还发布商用人形机器人智慧展览解决方案，将人形机器人与多媒体系统、云平台结合，提供统一管理与内容分发能力。[39] 年度业绩公告显示，公司在教育与服务机器人业务上持续投入，同时在工业与安防等新场景上探索人形机器人和服务机器人落地。[38]

技术上，优必选在模块化感知‑规划‑控制体系上逐步引入 AI 和大模型能力：在导航、视觉识别与语音交互方面采用深度学习算法，并通过云端平台实现内容和模型更新，同时保持底层运动控制模块的可靠性。[33][34][35][36][37][38][39]

### 4.3 宇树：四足与人形并行的模块化平台

宇树（Unitree）最早以四足机器人产品闻名，其产品页面展示了包括 Unitree Go2 等四足机器人以及 H1 等人形机器人，覆盖消费级、行业级和研究级市场。[40] 文章指出，宇树在伺服驱动器、电机和轻量化结构设计方面积累了大量经验，以此构建四足与人形共用的平台化架构。[40][41]

技术分析文章比较了 Tesla 与宇树的技术路线，指出两者在执行器、AI 算法、感知系统和应用场景上既有共性也有差异：宇树更强调在执行器和本体硬件上的高性价比与通用性，而在 AI 算法上采取渐进式引入策略，将深度学习与传统控制方法结合。[41] 报道提到，宇树通过持续推出新产品和迭代版本，覆盖从消费娱乐到工业和安防等多个市场，体现其平台化与模块化产品策略。[40][41][42]

宇树 H1 被定位为高性能人形平台，可用于研究与应用开发，并在公开资料中展示跑步、跳跃等高动态行为。[40] 媒体报道指出，宇树在业务上兼顾 B2B 与 B2C 市场，通过销售标准化平台和定制化解决方案，逐步拓展应用场景。[42] 总体而言，宇树的路线体现“模块化硬件平台 + 渐进式 AI 引入”的特点，在保持硬件可复用性的同时，通过软件和算法升级提升具身智能水平。[40][41][42][43]

### 4.4 工业机器人厂商：ABB/FANUC 等的升级方向

传统工业机器人领域的 ABB、FANUC 等公司长期采用模块化控制架构，系统通常包括独立控制柜、编程控制器和外部感知设备，强调高可靠性和可预测性。[12][13][47] 以 FANUC 为例，其资料介绍在机器人控制、伺服系统和 CNC 领域的发展，强调通过高精度伺服与控制器实现稳定、高速的工业自动化。[47]

随着具身智能和人形机器人热度提升，市场与产业研究报告指出，传统工业机器人厂商正探索通过增加更多感知模块、引入 AI 算法以及与大模型接口整合的方式，向更柔性和智能化系统升级。[11][12][13][14][10][15] 具体方向包括：

- 在视觉与力觉感知方面引入深度学习与自适应算法，提高在复杂工件和柔性生产中的适应能力；
- 通过数字孪生和仿真平台，与云端模型协同，优化生产节拍和路径规划；
- 探索与人形机器人厂商或大模型公司合作，将传统工业机器人与新一代具身智能系统联合部署。

公开资料尚未给出各家在大模型与具身智能上的详细路线图，但可以看出其基本路径仍基于模块化控制体系，逐步通过软件与感知升级实现“智能层”增强。[12][13][14][47][10][15]

### 4.5 落地场景与商业化进度

模块化路线在落地场景上具有明确行业聚焦：

1. **工业制造与仓储**  
   传统工业机器人厂商继续在焊接、搬运、装配等工序中保持优势，并通过增加柔性和感知能力拓展到小批量、多品种生产。[12][13][47][10][15] 优必选和宇树通过人形或四足平台切入物流、仓储和工厂巡检等场景，为企业提供补充性的自动化方案。[33][34][35][36][37][38][39][40][41][42][43]

2. **安防与巡检**  
   宇树的四足和部分人形平台被用于园区安防、工业设施巡检和应急响应等任务，利用其对复杂地形的适应性和远程控制能力。[40][41][42][43] 优必选在安防和公共服务领域也布局相关解决方案，利用人形与移动平台进行巡逻和信息发布。[33][34][35][37][39]

3. **展览与服务**  
   优必选在展览展示、政务服务和教育场景中有大量案例，通过人形机器人进行讲解、互动和表演，是人形机器人较早实现商业化的方向之一。[33][34][35][36][37][39]

在商业化进度上，模块化路线依托既有工业标准和服务市场，产品形态和商业模式相对成熟。优必选的年度业绩公告显示其已实现多元化收入来源，并在教育、服务与工业等领域有持续出货。[38] 宇树在消费与行业市场均有产品销售，并在 IPO 进程中获得资本市场关注。[58][59][61][40][41][42]

整体看，模块化路线在短期内更容易形成稳定收入来源，但在通用性和跨场景能力上相对端到端大模型路线存在差距，因此不少厂商正在探索通过“Large Behavior Models”和大模型接口实现二者融合。[12][13][14][40][41][42][44][45][46][10][15]

---

## 五、全球具身智能代表公司融资与资本格局

### 5.1 Figure：高估值与头部资本加持

多家媒体与数据平台报道显示，Figure 在 2024 年后连续完成大额融资，其估值在最新一轮中被报道为数十亿美元甚至更高。[48][49][50] 报道称，Figure 在一轮融资中获得约 10 亿美元资金，由多家大型科技企业和金融投资机构参与，使公司在尚未大规模量产前就获得“独角兽乃至更高等级”的市场估值。[49][50] 另有报道提到，在后续融资中，Figure 的估值被市场传言推升至约 390 亿美元级别，但这类数字多基于媒体和二级市场预期，存在不确定性。[48]

Figure 的投资方包括大型科技公司、产业基金和知名风投机构，体现具身智能领域“Big Tech + VC + 产业资本”深度参与的特点。[48][49][50] 高额融资为其进行大规模数据采集、模型训练和硬件迭代提供资源，也强化了市场对端到端大模型人形机器人路线的关注。[16][17][18][31][48][49][50]

### 5.2 1X：多轮融资与软银等机构的布局

1X 在 2023–2024 年间完成多轮融资。报道显示，2024 年 1 月公司完成一轮约 1 亿美元融资，投资方包括 EQT Ventures 等机构，使公司在向消费和企业市场拓展前获得资金支持。[51][52] Business Insider 报道进一步披露，这笔融资由多家机构共同参与，其中包括此前已投资公司的 OpenAI 等，反映出 AI 领域头部玩家对具身智能的持续兴趣。[52]

Crunchbase 的分析指出，软银（SoftBank）正在考虑主导一笔约 7500 万至 1 亿美元的新投资，用于支持 1X 的产品化与市场扩展，如果交易完成，将进一步提升公司在全球人形机器人赛道中的资本实力。[53] 1X 此前宣布在加利福尼亚建立生产设施并开启 NEO 人形机器人的生产，融资资金预计将用于扩大产能、优化供应链以及加大 Redwood AI 平台的研发投入。[27][28][54]

总体来看，1X 的融资规模虽低于 Figure，但在具身智能早期阶段已属较大体量，投资方结构多元，包含 AI 头部公司、金融机构和产业资本。[51][52][53][54]

### 5.3 Agility：多轮风险投资与潜在资本市场路径

数据平台与媒体报道显示，Agility Robotics 自成立以来完成多轮融资，投资方包括传统风投、产业资本以及与机器人和物流相关的企业。[55] 报道提到，2025 年的风险投资统计中，Agility 所在地区的 VC 活动接近 10 亿美元规模，Agility 被列为其中受关注的代表企业之一。[56]

资本市场分析文章指出，Agility 目前仍为未上市公司，但部分投资研究已讨论其潜在 IPO 机会，认为其可能在未来通过公开市场融资以扩大产能与全球布局。[57] 当前公开资料并未披露其详细估值或具体上市时间表，相关判断多基于市场推测和行业对人形机器人需求的预期。[55][56][57]

### 5.4 宇树与中国市场：IPO 进程与 ETF 关注

宇树在中国资本市场进展较快。财新报道指出，宇树计划在上海科创板（STAR Market）进行 IPO，拟募集资金规模约为数十亿元人民币，对应约 6 亿美元左右募资规模，反映资本市场对人形与四足机器人业务的看好。[58] 另一篇分析文章将宇树 IPO 与相关 ETF 的投资机会联系起来，指出以 STAR Market ETF 与人形机器人主题 ETF 为代表的产品正在关注宇树等公司的上市进程，并将其视为赛道标的之一。[59]

媒体报道还提到，宇树的人形机器人 G1 等产品被视为推动“机器人投资栈”重构的关键因素之一，认为其在硬件性能与成本控制上的优势有望推动下游应用扩张，进而带动相关 ETF 和主题基金的配置热度。[60][61]

总体而言，宇树通过 IPO 进入公开资本市场，将为其扩产、技术迭代和全球市场拓展提供资金支持，也为投资者提供直接参与具身智能硬件赛道的渠道。[58][59][60][61]

### 5.5 特斯拉、ETF 与赛道整体热度

在具身智能资本格局中，Tesla 既是产业参与者也是市场情绪的重要驱动因素。媒体报道中，Elon Musk 多次提出 Optimus 可能为 Tesla 带来十万亿美元级别长期市值贡献，认为人形机器人业务可能使 Tesla 成为 15–25 万亿美元市值公司，这些说法在投资者社区引发广泛讨论。[62][63] 相关分析指出，Tesla 计划在 AI 方向进行约 250 亿美元级别长期投资，涵盖自动驾驶与人形机器人，进一步强化市场对具身智能赛道的关注度。[64]

同时，多只聚焦人形机器人和具身智能的 ETF 开始出现。分析文章提到，包括以人形机器人和 STAR Market 为主题的 ETF 在内，正试图构建涵盖 Tesla、宇树等公司的指数化投资组合，以捕捉具身智能和人形机器人长期成长机会。[59][61][69] 另一篇文章专门讨论三只面向 Tesla Optimus 和 Figure AI 时代构建的人形机器人 ETF，这些产品往往通过持有相关芯片、工业自动化和机器人公司的股票，间接布局具身智能赛道。[69]

此外，行业资讯指出，在 2024–2025 年间，具身智能领域的日度融资总额在部分时间点已达到数亿元人民币级别，反映早期项目和上下游企业融资活动活跃。[68] 资金不仅流向人形机器人本体公司，也覆盖传感器、执行器、芯片和云服务等产业链环节。[68][13][14][10][15]

### 5.6 综合观察：资本格局的集中与分化

综合上述案例，可对当前（约 2023–2025/2026 年）具身智能与人形机器人资本格局作如下观察：

1. **头部公司高度集中大量资本**  
   Figure、1X、Agility、宇树等少数公司获得数亿美元甚至数十亿美元级别融资或 IPO 募资，成为各自技术路线标杆。[48][49][50][51][52][53][54][55][56][57][58][59][60][61]

2. **Big Tech 与产业资本深度参与**  
   Figure、1X 和 Agility 等均得到大型科技公司与产业方投资，Tesla 则通过自投模式推动 Optimus，体现大厂在具身智能方向的强烈布局意愿。[48][49][50][51][52][53][55][56][57][62][63][64]

3. **ETF 与二级市场放大赛道热度**  
   人形机器人主题 ETF 和 STAR Market ETF 等产品通过集中持仓具身智能相关公司，放大资本市场对该赛道的关注，并为投资者提供指数化配置工具。[59][61][69]

4. **估值分布与信息不对称**  
   部分公司估值主要来源于媒体报道与非公开交易预期，如 Figure 的高估值区间存在不同报道版本，而 Agility 等公司的估值与上市时间表尚未公开，提醒投资者在使用这类信息时需要关注“尚无公开数据”与“不确定性”。[48][49][50][55][56][57][58][59][60][61][68]

总体而言，具身智能赛道呈现“头部集中 + 主题扩散”的资本格局：少数公司集中大量资本与资源，而 ETF 和上下游企业则构成更广泛的生态投资网络。[48][49][50][51][52][53][54][55][56][57][58][59][60][61][62][63][64][68][69]

---

## 六、团队与人才结构：机器人公司 vs 大模型公司

### 6.1 Figure、1X 与 Agility：跨大模型与机器人背景的融合

公开公司简报与分析报告显示，Figure、1X 和 Agility 在团队构成上普遍呈现“机器人工程 + AI/大模型 + 大厂背景”的特征。[28][32][31] 

- 1X 的公司简报强调其创始人和核心成员具备在机器人与 AI 领域多年的经验，并提到公司获得 OpenAI 等 AI 领域头部企业的投资，这在一定程度上反映其在技术路线和人才来源上与大模型生态的紧密关联。[28][52]

- Agility 的公司简报指出，其团队核心成员来自机器人学与控制领域，并与高校和研究机构保持紧密合作，强调在动态机器人和仓储自动化上的专业积累。[32] 其与 NVIDIA 在基础模型与仿真平台上的合作也意味着团队需要同时具备机器人硬件工程与 AI 模型/仿真方面的人才结构。[30][31][32]

- 对 Figure 而言，现有资料主要聚焦技术路线和融资情况，但其与大模型公司以及工业客户的合作，结合其端到端 VLA 和互联网规模预训练路线，意味着团队需要兼具大模型算法、机器人控制和系统工程能力。[16][17][18][31][48][49][50]

整体上，这类“具身智能新创公司”往往在创始团队中包含来自大型科技公司（尤其自动驾驶、云计算与 AI 部门）、传统机器人公司以及学术界的成员，通过交叉背景推动大模型与机器人硬件融合。[28][32][31][52]

### 6.2 优必选与宇树：深厚本体与控制背景的机器人公司

优必选和宇树作为起步较早的机器人公司，其团队结构更偏向“机器人本体与控制 + 应用工程”。

优必选的公司介绍强调其核心团队长期深耕机器人本体、伺服驱动、运动控制和语音/视觉交互等领域，定位为“全栈机器人公司”，从核心部件到整机系统具备自研能力。[33][34][37] 在实际案例中，优必选在教育、安防、展览等场景大量部署人形和服务机器人，需要团队具备丰富的工程交付和项目实施经验。[35][36][37][39]

宇树方面，报道指出公司创始团队在机器人本体设计、执行器和控制系统方面有长期积累，其四足和人形平台体现动力学、结构设计与成本控制优势。[40][41][42] 分析文章提到，宇树在业务上强调硬件平台化和规模生产，这意味着其团队中制造工程、供应链管理和嵌入式控制人才占比较高。[40][41][42]

相比强调大模型算法的新创公司，优必选和宇树的团队更偏向传统机器人与硬件工程背景，在 AI 算法和大模型方向则采取与外部合作或渐进引入的方式。[33][34][37][40][41][42]

### 6.3 Boston Dynamics：研究导向的高端机器人团队

Boston Dynamics 是以高端研究与工程著称的机器人公司，其产品与内容强调在动力学控制、感知与运动规划上的前沿性。[44][46] Atlas 和“Perception and Adaptability”的介绍强调，通过结合传感器、感知算法和高带宽控制器，实现复杂行为和环境适应，这需要在机器人学、控制理论与软件工程方面高度专业的人才结构。[44][45][46]

提出“Large Behavior Models”后，Boston Dynamics 开始在行为层引入大规模数据驱动模型，这意味着其团队需要在传统机器人控制基础上进一步整合机器学习和大模型相关人才。[45] 相比完全以大模型为核心的新创公司，Boston Dynamics 的团队基础更偏向长期积累的机器人学知识，再在此之上叠加数据驱动方法。[44][45][46]

### 6.4 大模型公司 vs 机器人公司的人才结构差异

结合上述企业，可以概括大模型公司与机器人公司在具身智能方向上的人才结构差异：

1. **技术重心不同**  
   - 具身智能新创公司（如 Figure、1X、一定程度上的 Agility）在团队中更重视大模型算法、数据工程和云平台能力，同时需要机器人硬件和控制人才支撑落地。[16][17][18][28][31][32][52]  
   - 传统机器人公司（优必选、宇树、Boston Dynamics）以本体、执行器、控制和系统集成人才为主，在大模型方面多采取与外部合作或局部引入的模式。[33][34][37][40][41][42][44][45][46]

2. **业务导向差异**  
   - 以大模型为中心的公司强调构建可复用的平台与基础模型，希望通过云端服务和软件订阅获取长期收益，对数据与软件工程人才需求更大。[25][26][27][28][30][31][32]  
   - 传统机器人公司更侧重硬件销售、项目交付与售后服务，需要大量现场工程师和系统集成人才。[33][34][35][36][37][38][39][40][41][42]

3. **合作模式与生态位**  
   - 部分具身智能公司与大模型公司之间存在投资与技术合作关系，如 1X 获得 OpenAI 投资并利用云端 AI 平台增强产品能力。[28][52]  
   - 传统机器人公司则可能与云计算和 AI 服务商合作，将机器人作为具身载体接入外部大模型，从而在不大幅改变团队结构的前提下升级产品智能水平。[12][13][14][33][34][35][36][37][38][39][40][41][42][44][45][46]

需要指出的是，现有公开资料对各公司创始人与核心团队的具体成员履历、人数结构等信息披露有限，本节更多基于公司定位、合作信息和业务特征进行定性总结，而不涉及未公开的具体数据。[28][32][33][34][37][40][41][42][44][45][46]

---

## 七、综合评估与趋势

### 7.1 技术路线的短中期商业化前景

从端到端大模型控制与模块化感知‑规划‑控制两大路线看，短中期（3–5 年）内两者将并行发展，并在不同场景中形成差异化优势。

- **端到端大模型路线**  
  Figure、Tesla、Google DeepMind RT 系列、1X 和 Agility 等代表企业通过 VLA、基础模型与云端平台探索跨任务泛化和持续学习。[16][17][18][19][20][21][22][23][24][25][26][27][29][30][31][32][51][52][53][54] 商业化上，多处于原型与试点阶段，重点场景包括制造、仓储、安防和服务等，需要进一步验证安全性、可靠性和成本。[18][19][71][72][27][28][29][30][32][54]

- **模块化路线**  
  Boston Dynamics、优必选、宇树以及 ABB/FANUC 等在工业和服务场景中已有大量落地项目，商业模式成熟。[12][13][33][34][35][36][37][38][39][40][41][42][43][44][45][46][47] 随着“Large Behavior Models”和大模型接口引入，这一路线有望在保持工程可靠性的前提下提升智能水平，短期内更易形成稳定收入和现金流。[12][13][14][44][45][46][10][15]

综合来看，在 3–5 年时间尺度内，模块化路线在工业和安防等高可靠场景中仍将占据主导，而端到端大模型路线更可能在灵活性和多任务场景中率先展现差异化价值，尤其在与云端平台结合的企业服务模式中。[1][2][3][6][7][8][9][31][11][12][13][14][10][15]

### 7.2 关键技术难点

当前具身智能发展面临若干关键技术难点：

1. **数据与模型规模**  
   端到端 VLA 与基础模型需要大规模、多样化机器人数据和互联网数据，对数据采集、标注与训练基础设施提出高要求。[2][3][70][16][17][20][21][22][23][24][31] Figure 的 Project Go‑Big 和 Google 的 RT‑2 等项目体现向“互联网规模预训练”的趋势，但也带来成本与可持续性挑战。[16][17][20][21][22][23][24]

2. **安全与可验证性**  
   在工业与公共环境中部署具身智能，需要确保复杂环境和边界条件下的安全行为。模块化路线通过分模块验证具有优势，而端到端路线需要新的验证与监控方法。[1][2][3][7][8][12][13][14][44][45][46]

3. **本体与执行器技术**  
   人形机器人在动力学、执行器、减速器和能量密度等方面仍存在工程挑战。优必选和宇树等企业通过自研核心部件和平台化架构降低成本，但在大规模量产和可靠性方面仍需持续投入。[33][34][37][40][41][42][43][10][15]

4. **云‑边协同与实时性**  
   云端大模型 + 边缘执行架构需要在通信延迟、带宽和安全之间取得平衡，确保网络不稳定时机器人仍能安全运行。[6][7][8][9][25][26][27][28][54][11][12][13][14][10][15]

### 7.3 资本偏好与赛道演化

资本市场在具身智能赛道上呈现以下偏好与趋势：

- **偏好头部平台型公司**  
  Figure、1X、Agility 和宇树等具备平台化产品与清晰技术路线的公司获得大额融资或 IPO 机会，反映资本对“平台 + 生态”型企业的偏好。[48][49][50][51][52][53][54][55][56][57][58][59][60][61]

- **关注大模型叙事与商业落地结合**  
  Figure 的 VLA 路线、1X 的 Redwood AI 平台和 Agility 与 NVIDIA 的基础模型合作均获得资本市场关注，说明投资者看重大模型叙事与具体场景落地的结合。[16][17][25][26][27][29][30][31][32][51][52][53]

- **ETF 与主题基金推动赛道扩散**  
  人形机器人与 STAR Market 主题 ETF 通过指数化配置放大赛道热度，使更多投资者可以间接参与具身智能相关公司。[59][61][69]

然而，部分估值数据主要来自媒体报道与非公开市场预期，信息不对称和预期波动带来风险，投资者在评估时需注意数据来源可靠性与时间敏感性。[48][49][50][55][56][57][58][59][60][61][68]

### 7.4 人才配置与生态合作

在人才与组织层面，具身智能发展呈现“机器人公司”和“大模型公司”两种组织基因的融合：

- 端到端路线企业倾向于同时布局大模型算法、数据工程、云平台和机器人控制人才，并通过与大模型公司或云平台合作进一步强化能力。[16][17][18][25][26][27][28][30][31][32][52]

- 传统机器人企业在本体与控制领域保持优势，通过与外部 AI 服务商合作或内部组建小规模 AI 团队实现能力升级。[33][34][35][36][37][38][39][40][41][42][44][45][46]

这一趋势意味着，在未来 3–5 年内，具身智能生态很可能由多方协同构成：大模型提供感知与决策能力，机器人公司提供本体与控制系统，云平台与系统集成商负责部署和运维。[6][7][8][9][31][11][12][13][14][10][15]

---

## 八、局限与后续研究方向

### 8.1 本次研究的证据边界

本报告基于公开文献、公司发布和市场研究报告，对全球具身智能技术路线及代表性公司进行了梳理。[1][2][3][4][5][6][7][8][9][70][11][12][13][14][33][34][35][36][37][38][39][40][41][42][43][44][45][46][47][10][15] 主要局限包括：

1. **估值与融资数据不确定性**  
   部分公司（如 Figure、Agility 等）的估值和融资金额主要来自媒体报道与数据平台，存在口径差异，且部分交易条款未完全公开。[48][49][50][55][56][57][58][59][60][61][68] 因此，本报告仅以“约”“区间”“公开披露”方式引用，不对未披露数据进行推断。

2. **产品部署与出货规模披露不足**  
   多数人形机器人企业仅展示样机和试点案例，对实际部署数量、出货规模和客户结构尚无全面公开数据，本报告在描述时仅限于“实验室原型”“试点”“小批量生产”等定性表述。[18][19][71][72][27][28][29][30][32][54][33][34][35][36][37][38][39][40][41][42][43]

3. **团队与人才结构信息有限**  
   除少数公司外，多数企业未在公开渠道详细披露创始团队成员背景、团队规模和内部组织结构，本报告仅基于公司定位与公开合作信息做定性分析。[28][32][33][34][37][40][41][42][44][45][46]

4. **区域与公司覆盖不完全**  
   尽管引用了覆盖 95+ 家人形机器人企业的调研报告与多份市场研究，[11][10][15] 本报告在具体公司分析上主要聚焦 Figure、Tesla、Google DeepMind、1X、Agility、Boston Dynamics、优必选、宇树等代表性企业，未对所有公司逐一展开。

### 8.2 后续研究方向

基于上述局限，后续研究可从以下方向深化：

1. **细化场景与经济性分析**  
   结合具体工厂、仓储和服务场景，对人形与非人形形态在资本支出、运营成本和回收期上的差异进行定量研究，目前公开文献在这方面数据较少。[6][7][8][9][11][12][13][14][10][15]

2. **跨公司技术栈对比与标准化研究**  
   系统比较不同公司在感知、规划、控制和大模型接口上的技术栈，研究标准化接口和通用中间件对生态的影响，尤其是云‑边协同和多机器人平台支持方面。[1][2][3][4][5][70][20][21][22][23][24][25][26][27][30][31][44][45][46]

3. **长期安全与伦理问题**  
   在具身智能大规模部署前，需进一步研究其在安全、隐私、伦理和劳动力市场等方面的影响，目前相关讨论多停留在概念层面，缺乏长周期实证数据。[1][2][3][7][8][9]

4. **资本与政策的交互影响**  
   结合各国政策（如先进制造、智能机器人扶持计划等）与资本市场行为，研究政策驱动与市场驱动在具身智能产业发展中的相互作用。[12][13][14][10][15]

随着更多产品进入量产、更多公司披露运营与财务数据，以及新的学术与产业研究出版，本报告所述结论与判断也需要定期更新，以反映具身智能技术路线与资本格局的最新演进。

---

## 参考文献

[1] A Comprehensive Survey on Embodied Intelligence: Advancements, Challenges, and Future Perspectives https://www.sciopen.com/article/10.26599/AIR.2024.9150042

[2] Large Model Empowered Embodied AI: A Survey on Decision-Making and Embodied Learning https://arxiv.org/html/2508.10399v1

[3] Embodied AI: From LLMs to World Models https://mn.cs.tsinghua.edu.cn/xinwang/PDF/papers/2025_Embodied%20AI%20from%20LLMs%20to%20World%20Models.pdf

[4] A SURVEY OF EMBODIED ARTIFICIAL INTELLIGENCE DATA … https://airs.cuhk.edu.cn/sites/default/files/2025-06/Survey_Arxiv.pdf

[5] Paper List and Resource Repository for Embodied AI https://github.com/HCPLab-SYSU/Embodied_AI_Paper_List

[6] Embodied Intelligence Robots Market Research Report https://www.reemanrobot.com/news/w-84952931.html

[7] Embodied AI Market Report (Grand View Research) https://www.grandviewresearch.com/industry-analysis/embodied-ai-market-report

[8] Embodied AI Market Report (MarketsandMarkets) https://www.marketsandmarkets.com/Market-Reports/embodied-ai-market-83867232.html

[9] Embodied AI Market Report (Congruence Market Insights) https://www.congruencemarketinsights.com/report/embodied-ai-market

[10] 2024-2025年具身智能与人形机器人市场研究（摘要） https://db.shujubang.com/home/login/index/gid/21100

[11] 国外人形机器人产品梳理 https://pdf.dfcfw.com/pdf/H3_AP202311141610688991_1.pdf

[12] 人形机器人发展与展望 https://pdf.dfcfw.com/pdf/H3_AP202309061597741928_1.pdf

[13] 2023年机器人行业调研报告：人形机器人的国产供应链机遇 https://yiqifu.baidu.com/cknowledge_10114222268

[14] 人形机器人系列（1）：产业跃迁：政策驱动、技术拐点与场景革命的三重共振 https://aigc.idigital.com.cn/djyanbao/【交银国际证券】人形机器人系列（1）：产业跃迁：政策驱动、技术拐点与场景革命的三重共振-2025-04-02.pdf

[15] 240729 全球95+家人形机器人企业深度调研 https://www.scribd.com/document/923874269/240729-%E5%85%A8%E7%90%8395-%E5%AE%B6%E4%BA%BA%E5%BD%A2%E6%9C%BA%E5%99%A8%E4%BA%BA%E4%BC%81%E4%B8%9A%E6%B7%B1%E5%BA%A6%E8%B0%83%E7%A0%94

[16] Project Go‑Big: Internet-Scale Humanoid Pretraining and Control with Helix 03 https://www.figure.ai/news/project-go-big

[17] Helix: A Vision-Language-Action Model for Generalist Humanoid Robots https://www.figure.ai/news/helix

[18] Introducing Figure 03 https://www.figure.ai/news/introducing-figure-03

[19] AI & Robotics | Tesla https://www.tesla.com/AI

[20] RT-1: Robotics Transformer for real-world control at scale https://research.google/blog/rt-1-robotics-transformer-for-real-world-control-at-scale/

[21] RT-1: Robotics Transformer for Real-World Control at Scale https://arxiv.org/abs/2212.06817

[22] RT-2: New model translates vision and language into action https://deepmind.google/blog/rt-2-new-model-translates-vision-and-language-into-action/

[23] RT-2 Project Page https://robotics-transformer2.github.io/

[24] RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control https://arxiv.org/abs/2307.15818

[25] Redwood AI | 1X https://www.1x.tech/discover/redwood-ai

[26] Redwood AI Mobility | 1X https://www.1x.tech/discover/redwood-mobility

[27] 1X’s NEO humanoid gains autonomy with new Redwood AI model https://www.therobotreport.com/1xs-neo-humanoid-gains-autonomy-with-new-redwood-ai-model/

[28] 1X Company Brief | Contrary Research https://research.contrary.com/company/1x

[29] Industrial Humanoid Automation | Agility https://www.agilityrobotics.com/

[30] Agility Robotics Expands Relationship with NVIDIA https://www.agilityrobotics.com/content/agility-robotics-expands-relationship-with-nvidia

[31] Robotics in the Era of Foundation Models https://agentic.substack.com/p/robotics-in-the-era-of-foundation

[32] Agility Robotics Company Brief | Contrary Research https://research.contrary.com/company/agility-robotics

[33] 优必选科技： 让智能机器人走进千家万户 https://www.worldrobotconference.com/uploads/exfile/video/xb3etl.pdf

[34] 关于优必选科技 - UBTECH Robotics https://www.ubtrobot.com/cn/about/company-profile

[35] Application Scenarios https://www.ubtrobot.com/cn/humanoid/application-scenarios

[36] 直击WAIC2021：Walker X全球首发，优必选科技全栈解决方案加速AI应用落地 https://www.pingwest.com/a/245586

[37] 一线案例丨优必选：深耕核心技术，练就独家本领 https://www.stdaily.com/web/gdxw/2026-03/06/content_481315.html

[38] 截至2025 年12 月31 日止年度之年度業績公告 https://stockn.xueqiu.com/09880/20260331095340.pdf

[39] 优必选发布商用人形机器人智慧展览解决方案，重塑服务新体验 https://www.aibangbots.com/a/1866

[40] 宇树机器狗（Unitree Go2 / H1 产品页） https://www.unitree.com/operate/robot

[41] 特斯拉与宇树机器人技术路线对比：执行器、AI算法、感知、应用等 https://www.aibangbots.com/a/972

[42] 宇树科技的AB面 https://www.tmtpost.com/7946634.html

[43] 解锁人形机器人（图） https://epaper.tianjinwe.com/tjrb/html/2024-07/11/content_143090_1031007.htm

[44] Atlas Humanoid Robot - Boston Dynamics https://bostondynamics.com/products/atlas/

[45] Large Behavior Models and Atlas Find New Footing https://bostondynamics.com/blog/large-behavior-models-atlas-find-new-footing/

[46] Perception and Adaptability | Boston Dynamics https://bostondynamics.com/video/perception-and-adaptability/

[47] 2018-Ⅱ - ファナック株式会社(FANUC CORPORATION) https://www.fanuc.co.jp/en/profile/news/pdf/fanucnews2018ii_c.pdf

[48] Robotics startup Figure valued at $39 billion in latest funding round https://finance.yahoo.com/news/figure-valued-39-billion-latest-131115237.html

[49] Figure AI passes $1B with Series C funding toward humanoid robot development https://www.therobotreport.com/figure-ai-raises-1b-in-series-c-funding-toward-humanoid-robot-development/

[50] Robotics Funding Crests Higher As Figure Lands Another $1B https://news.crunchbase.com/robotics/ai-funding-high-figure-raise-data/

[51] Humanoid robot startup 1X raises $100M to move into the consumer market https://siliconangle.com/2024/01/11/humanoid-robot-startup-1x-raises-100m-move-consumer-market/

[52] This OpenAI-backed startup builds humanoid robots. It just raised $100 million with this 13-slide pitch deck. https://www.businessinsider.com/1x-openai-robotics-startup-raises-100-million-from-eqt-ventures-2024-1

[53] SoftBank Looking At Leading A $75M To $100M Investment In 1X Technologies — Report https://news.crunchbase.com/ai/softbank-humanoid-robotics-investment-1x-tech/

[54] 1X begins production of NEO humanoids in California facility https://www.therobotreport.com/1x-begins-production-neo-humanoid-robots-at-hayward-california-facility/

[55] Agility Robotics - 2026 Funding Rounds & List of Investors https://tracxn.com/d/companies/agilityrobotics/__zWyvO8soXb6xhR16FWzvRmbHXslWot5BI_JRbmtdaF0/funding-and-investors

[56] Venture Capital activity nears $1B in 2025 https://www.bizjournals.com/portland/news/2026/01/21/venture-capital-activity-jumps-in-2025.html

[57] Agility Stock: Can You Invest Before the IPO? https://accessipos.com/agility-robotics-stock-ipo/

[58] Humanoid Robot Maker Unitree Advances Toward $618 Million Shanghai IPO https://www.caixinglobal.com/2026-06-02/humanoid-robot-maker-unitree-advances-toward-618-million-shanghai-ipo-102449940.html

[59] A Complete Guide To Unitree Robotics’ 2026 IPO, Why It Matters For STAR Market ETF KSTR & Humanoid Robotics ETF KOID https://kraneshares.com/a-complete-guide-to-unitree-robotics-2026-ipo-why-it-matters-for-star-market-etf-kstr-humanoid-robotics-etf-koid/

[60] The Biggest Winner in the Background Emerges Behind Unitree's IPO https://eu.36kr.com/en/p/3835853052392576

[61] Unitree G1 Humanoid Robots Are Reshaping The Robotics Investment Stack https://www.forbes.com/sites/jonmarkman/2026/04/27/unitree-g1-humanoid-robots-are-reshaping-the-robotics-investment-stack/

[62] Elon Musk says Optimus robots could make Tesla $25 trillion company https://www.cnbc.com/2024/06/13/elon-musk-says-optimus-robots-could-make-tesla-25-trillion-company-.html

[63] Elon Musk Sees $15 Trillion Optimus Upside — Tesla Investors Could Get A Piece For 'Free' https://finance.yahoo.com/markets/stocks/articles/elon-musk-sees-15-trillion-193109583.html

[64] Tesla’s $25B AI Investment: Musk’s Big Bet Amid Rising Competition https://www.motortrend.com/news/tesla-25-billion-ai-investment-musk-robotaxi-optimus-analysis

[65] Xiaomi, HongShan back X Square Robot in Series B round https://kr-asia.com/xiaomi-hongshan-back-x-square-robot-in-series-b-round

[66] Xiaomi Enters Robotics Core Components, Invests in Joint Tech Firm "Guohua Intelligence": Yingke Exclusive Report https://eu.36kr.com/en/p/3454790669260416

[67] Xiaomi deploys humanoid robots in EV factory for auto assembly https://cnevpost.com/2026/03/02/xiaomi-deploys-humanoid-robots-ev-factory/

[68] Daily Fundraising Exceeds 300 Million Yuan as Embodied AI Sector Surges https://autonews.gasgoo.com/articles/icv/daily-fundraising-exceeds-300-million-yuan-as-embodied-ai-sector-surges-2042234221655924737

[69] Three Humanoid Robotics ETFs Built for the Tesla Optimus and Figure AI Era Most Investors Have Never Heard Of https://www.aol.com/articles/three-humanoid-robotics-etfs-built-170504000.html

[70] Multi-agent Embodied AI: Advances and Future Directions http://arxiv.org/abs/2505.05108v2

[71] Optimus can now sort objects autonomously. Its neural network is trained fully end-to-end: video in, controls out. https://www.reddit.com/r/teslainvestorsclub/comments/16qjgfj/optimus_can_now_sort_objects_autonomously_its/

[72] Watch: Tesla's humanoid robot shows yoga moves, greets 'Namaste' https://timesofindia.indiatimes.com/etimes/trending/watch-teslas-humanoid-robot-shows-yoga-moves-greets-namaste/articleshow/103954414.cms
