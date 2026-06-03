## 2022–2026年全球具身智能技术路线与代表性公司研究：中美欧对比

---

## 摘要

2022–2026 年，具身智能经历从单机 Demo 向“通用具身平台 + 大模型”阶段的快速跃迁。多篇综述与行业报告显示，多模态大模型、世界模型与传统机器人自治栈正在加速融合，ABC 框架（AI 大脑–机器人本体–多模态传感器）逐渐成为描述具身系统的通用抽象。[1][2][3][4][5][6]

在技术路径上，可归纳出四条主流路线：端到端 Vision‑Language‑Action（VLA）/动作基础模型控制、具身 LLM + 分层控制、世界模型 + 规划控制、传统分层自治栈 + 学习增强。[7][8][9][10][11][12] 这些路线与人形 / 四足 / 轮式等硬件形态以及工业、物流、服务等应用场景紧密耦合。

从区域看，美国在通用人形机器人（Tesla、Figure、Agility、Apptronik、Sanctuary）和大模型机器人平台（RT‑2、Gemini Robotics、ELLMER）上处于前沿，展现出“AI 基础模型 + 通用人形硬件 + 高强度资本投入”的组合。[13–42] 中国在华为 Pangu 世界模型、优必选 Walker 系列、傅利叶 GR‑1、西湖 Titan O1 等方向形成以政策牵引、世界模型云平台、工业场景为重点的路线。[43–52] 欧洲则更多体现为传统高可靠腿式/巡检平台（ANYmal）与工业级人形/四足控制栈（Boston Dynamics）基础上的持续演进。[53–60]

资本层面，人形与通用具身机器人在 2023–2026 年出现融资放量，Figure AI 与 Apptronik 单轮融资规模分别达到约 6.75 亿美元和 5.2 亿美元，被视为“从试点走向平台化商业”的信号。[29–31][61–64] 但行业整体仍处“试点到早期量产”阶段，订单规模、单机成本和可靠性尚未成熟。[31][65][66]

人才与团队方面，具身智能项目普遍由顶级自动驾驶、机器人和大模型背景的创始人和技术团队主导，以美国大型科技公司与创业公司集聚最为明显。[32][40][67][68] 中国则体现为大厂云部门与机器人公司协同；欧洲则由传统机器人企业与研究机构主导。[43–45][53–55]

受限于现有证据，本报告在细化各公司收入规模、具体估值、团队详细履历等维度上存在信息不足。以下分析基于公开论文、企业公告与行业研究报告，重点呈现技术路线、代表性公司和区域对比。

---

## 一、研究范围与方法

本报告聚焦 2022–2026 年全球具身智能的发展，重点关注：

- 技术路线：包括模型架构（VLA、大语言模型、世界模型、强化学习、模仿学习等）、控制架构与训练范式。[1][7][9][10][11][69][70]
- 硬件/平台：人形、四足、轮式与工业巡检等具身载体。[2][53][54][59][71]
- 区域对比：美国、中国、欧洲在技术路径、代表性公司、产品进度与商业化阶段的差异。[13–16][29–31][43–45][53–55]
- 融资与资本：典型公司融资规模、节奏及其产业化含义。[29–31][61–64][65][66][72]
- 团队与人才：创始人与核心技术团队背景与所在地区生态的关系。[32][40][67][68]

方法上，本报告依托：

1. 具身智能综述与特写：系统梳理具身 AI 研究目标、ABC 组成与从 LLM 到世界模型的技术演进。[1–6][69][70]
2. 大模型驱动具身系统案例：如 RT‑2、Gemini Robotics、ELLMER、GAE 等。[13–18][20–23][36–38][46–48]
3. 代表性机器人公司官方资料、媒体报道与行业报告：覆盖 Figure AI、Tesla、Agility、Apptronik、Sanctuary、优必选、傅利叶、西湖、ANYbotics、Boston Dynamics 等。[19–22][24–31][33–35][39–42][43–45][49–52][53–60][61–66][71–75]
4. 市场与资本研究：Omdia 市场雷达、KraneShares、Robozaps 行业盘点等。[59][60][65][66][72]

局限性说明：

- 融资金额、估值和客户收入等多为区间或定性描述，缺乏系统财务数据。[29–31][61–64][65][66]
- 部分中国与欧洲公司的控制架构与算法细节披露有限，仅能基于公开信息进行高层归纳。[43–45][49–52][53–55]
- 团队背景多为局部报道，无法形成完整的人才图谱。

---

## 二、全球具身智能技术路线综述

### 2.1 研究目标与系统抽象：从四大目标到 ABC 框架

最新具身 AI 综述将具身 AI 研究目标划分为四个方面：具身感知、具身交互、具身智能体和仿真到现实迁移。[1][3] 这四个目标分别对应：

- 多模态感知：如何通过视觉、触觉等跨模态传感器获取环境与物体信息；
- 人机交互：自然语言、手势等交互方式；
- 策略学习与智能体：包括强化学习、模仿学习、世界模型驱动的决策；
- Sim‑to‑real：如何将仿真环境中学到的策略可靠迁移到现实机器人。[1][3]

为统一描述具身系统组成，综述提出 ABC 框架：

- A – AI Brain：包括具身世界模型与大模型（LLM/VLM），承担感知理解、世界建模与高层决策功能；[2][4][5]
- B – Body：机器人本体与执行机构，如人形、四足、轮式平台及机械臂；[2]
- C – Cross‑modal Sensors：跨模态传感器，包括视觉、激光、力/扭矩与触觉等，用于支撑具身感知与交互。[2][4][5]

多模态大模型（Multi‑modal Large Models）与世界模型（World Models）在 2022–2024 年间逐渐成为具身代理的重要架构，用于统一数字环境与物理环境中的感知与决策。[5][6][69–72]

### 2.2 四大技术路线

基于多篇综述与代表系统，可将当前具身智能技术路径归纳为四类：[7–12][69–72]

1. **端到端大模型控制路线（VLA / 动作基础模型）**

   代表系统：Google DeepMind RT‑2、Figure Helix、1X Redwood、西湖 GAE 等。[13–18][19–22][24–28][46–48]

   - 架构特点：采用 Transformer 类 VLA 模型，将视觉和语言输入直接映射为动作 token 或控制命令，实现端到端控制。
     - RT‑2 将互联网规模视觉‑语言模型扩展为 Vision‑Language‑Action 模型，通过联合训练 web 图文数据和机器人动作数据，将 Web 知识迁移到机器人控制，能理解抽象自然语言并执行多步任务。[13–18][20–23]
     - Figure Helix 被描述为通用 VLA 模型，从摄像头视觉和语言指令生成动作控制信号，在少量机器人数据微调下实现跨任务泛化，并端到端集成至 Figure 人形机器人。[19–22]
     - 1X Redwood 是面向 humanoid 的 vision‑language Transformer，可从传感器输入直接生成控制命令，实现家庭与室内环境中的端到端移动操作任务。[24–28]
     - Westlake GAE（General Action Expert）是通用动作基础模型，可在多机器人实例上运行，模仿人类行为并跨场景执行任务，驱动 Titan O1 人形。[46–48]
   - 训练范式：互联网图文预训练 + 机器人数据联合训练或微调。[13–18][19–22][24–28][46–48]
   - 优势与挑战：具备较强的任务泛化能力，但高度依赖大规模数据和算力；安全、对齐和可解释性是主要挑战。[7][11]

2. **具身 LLM + 分层控制路线**

   代表系统：Nature 发表的 ELLMER 框架、Sanctuary Carbon 认知架构、部分 Tesla/1X 的“高层 AI + 低层控制”等。[33–42][24–28][36–38]

   - 架构特点：LLM 或多模态大模型主要承担高层任务理解与规划，低层控制由传统控制器、技能库或学习型控制策略执行。
     - ELLMER 使用 GPT‑4 和检索增强生成（RAG）作为高层规划与推理模块，将感知结果编码为文本或语义表示，通过任务分解与规划输出低层控制命令，使机器人在家庭等不可预测环境中完成清洁、整理、取物等复杂任务。[33–38]
     - Sanctuary Phoenix 的 Carbon 认知架构将自然语言指令转换为动作，集成语言理解、任务规划和感知整合，驱动 humanoid Phoenix 执行广泛现实任务。[39–42]
   - 优势与挑战：易于接入现有 LLM 能力（推理、工具调用、RAG），利于安全约束设计；但系统复杂度高，实时性与鲁棒性对接口设计要求极高。[7][9][10]

3. **世界模型 + 规划/控制路线**

   代表系统：DeepMind/Meta 世界模型研究、华为 Pangu 世界模型、Agility+NVIDIA 仿真基础模型等。[8][43–45][55–58][69–72]

   - 概念：世界模型通过建模外部环境推断和预测真实世界动力学，已成为具身 AI 的关键组成，用于支持规划与决策。[69–72]
   - 技术类型：潜在动力学模型、生成式模型、基于 Transformer 的世界模型广泛应用于强化学习、规划和控制，并与 LLM/VLM 结合。[70–72]
   - 中国代表：华为的 Pangu 世界模型可为智能驾驶和 embodied AI 机器人生成数字物理空间，用于连续训练和复杂场景模拟；并提出基于 6G 的云端大模型控制原型，通过云端基础模型统一机器人感知、决策和控制。[43–45]
   - 行业实践：Agility Digit 使用 NVIDIA Isaac Sim 和 Isaac Lab 在仿真环境中训练“全身控制基础模型”，再部署到真实 Digit，借助仿真‑现实数据闭环优化策略。[55–58]

4. **传统分层自治栈 + 学习增强路线**

   代表系统：Boston Dynamics Atlas 与 Spot、Agility Digit、ANYbotics ANYmal 以及大量工业/物流机器人公司。[53–60][73–75]

   - 架构：沿用经典感知–规划–控制分层架构（SLAM/建图/物体识别–路径与行为规划–轨迹及全身控制），在局部（如步态生成、抓取策略）引入深度学习、强化学习或模仿学习。[7][10][72]
   - 代表实践：
     - Boston Dynamics 在 Atlas、Spot、Stretch 之间复用模块化运动生成和基于行为树的任务控制平台，通过多模态传感器构建环境模型，实现对不同地面和障碍的自适应。[53–58]
     - ANYmal 集成激光雷达与摄像头等多种传感器及高级状态估计算法，在复杂地形实现自主行走，同时提供开放软件栈和 API 支持研究机构自定义感知和控制算法。[53–54][73–75]
     - 优必选 Walker S 在传统视觉伺服和柔顺控制基础上融合强化学习与模仿学习，提高工业装配等任务的鲁棒性与泛化。[49–51]
   - 特点：安全性、可靠性高，便于工业客户接受，但在开放环境泛化与自然语言理解方面相对受限，需要逐步与大模型/世界模型结合。[7][10][72]

### 2.3 硬件/平台谱系与应用场景

Omdia 对“通用具身智能机器人”市场的梳理指出，人形与非人形（轮式、履带式等）多种硬件形态并存，应用领域包括工业、物流和服务等。[59][60] 典型平台包括：

- **人形机器人**：Tesla Optimus、Figure 01/02/03、Agility Digit、Apptronik Apollo、Sanctuary Phoenix、优必选 Walker 系列、傅利叶 GR‑1、西湖 Titan O1、丰田 T‑HR3 等。[19–22][24–31][33–42][43–52][61–66][71–75]
- **四足/腿式平台**：ANYbotics ANYmal、Boston Dynamics Spot/Atlas（高动态双足/多足）。[53–58][73–75]
- **移动+机械臂**：RT‑2 所针对的机械臂与移动平台、Gemini Robotics 支持的移动机器人与实验室助手等。[13–18][36–38]

应用场景集中在：

- 仓储与物流：Digit 在 Amazon 仓库搬运塑料箱；ANYmal 在苛刻工业环境执行巡检；多款人形（Figure、Apollo）面向仓储和物料搬运。[27–28][55–58][61–64][73–75]
- 制造与工业装配：Tesla Optimus 在 Fremont 和 Austin 工厂内部搬运与物料转运；Figure 在汽车厂与制造场景进行试点；优必选 Walker S2 面向装配任务；Atlas 定位于物料搬运与智能自动化。[29–31][40–45][49–52][53–56]
- 服务与家庭场景：Sanctuary Phoenix 面向家务清洁与服务；1X NEO 面向家庭任务；未来乐观预期包括家庭助理和服务业等。[24–28][39–42][71–75]

---

## 三、美国具身智能代表性公司与技术路线

### 3.1 Figure AI：端到端 VLA + 大模型协同的人形平台

**定位与技术路径**

Figure AI 约于 2022 年成立，由 Brett Adcock 创立，专注通用人形机器人，目标在工业环境中与人类协同工作。[32][40] Figure 机器人采用类似人类的头部、躯干、双臂和双腿的人形设计，面向制造和物流等场景执行搬运、拣选、物料配送等任务，依赖先进 AI 模型进行感知和决策，并通过软件升级赋予新技能。[19–22][32][40]

技术路线：

- 硬件：双足人形、电驱动、模块化关节，强调安全和人机协作。[19–22][32]
- 软件：结合机器学习、强化学习与大模型能力，使机器人在非结构化环境中通过自然语言指令执行任务，并与 OpenAI 等合作，将通用大模型的理解与规划能力集成到平台。[32][40][68]
- Helix VLA 模型：作为通用 Vision‑Language‑Action 模型，从摄像头视觉和语言指令生成动作控制信号，在少量机器人数据微调下实现跨任务泛化，并端到端集成至 Figure humanoid。[19–22]

**产品与时间线**

- Figure 01：首台成熟双足人形原型，具备多关节手臂与手，可进行抓取、搬运和工具使用，2023–2024 年主要用于技术验证和演示。[32][40]
- Figure 02：在 Figure 01 基础上提升感知与操作能力，面向物流和制造场景。[19–22][40]
- Figure 03：面向工业场景、可规模生产部署的通用人形机器人，是迈向可部署机器人车队的关键产品。[75]

Figure 在 2023–2024 年展示 Figure 01 原型并宣布多家企业试点，2024–2025 年通过大额融资推进量产工厂布局和首批客户部署。[19–22][29–31] Notebookcheck 报道其第二代人形机器人已在 2025 年向首位客户实现正式交付。[30][31]

**商业化与融资**

- 商业化：与汽车厂（如 BMW）与仓储企业开展试点部署，用于生产和物流流程中的物料搬运与支持任务。[32][40][41]
- 融资：2024 年完成约 6.75 亿美元融资，投资者包括 OpenAI、微软、英伟达和 Jeff Bezos 等，资金用于建设生产线和推进量产与商业化试点。[29][31][65][66][72]

### 3.2 Tesla：自动驾驶 AI 栈延伸的人形 Optimus

**技术路径与架构**

Tesla 将自动驾驶中的 AI 堆栈延伸至人形机器人 Optimus：Optimus 采用基于摄像头的视觉感知、多摄像头 3D 占据网络以及端到端神经网络，并使用大量视频数据训练，以统一感知、规划和控制。[26–28][35–37]

- 从模块化“感知‑规划‑控制”向单一端到端神经网络迁移，目标是从原始视频直接输出控制指令。[26–27]
- 训练策略结合模仿学习（人类演示）、仿真任务与强化学习。[28]

**产品与部署**

- 时间线：AI Day 2021 提出 Tesla Bot 概念；2022 年展示早期原型；2023–2024 年发布动作更自然的 Optimus Gen 2，改善机械结构和运动能力。[35–37]
- 规格与定位：Optimus Gen 2 身高约 173 cm、重量约 57 kg，目标售价 2–3 万美元，定位为 Tesla 工厂中的通用劳动力机器人。[35–37]
- 部署：2024 年起已在 Fremont 与 Austin 工厂内部部署，用于搬运和物料转运等重复任务。截至 2026 年，主要用于内部试点和演示，批量制造但尚未对外量产销售。[35–37]

Robozaps 对比指出，Optimus 相比约 1.6 万美元的 Unitree G1 更偏向工业工厂应用，体现不同定位与价格策略。[37][71][72]

### 3.3 Agility Robotics：Digit 与全栈自主+仿真基础模型

Agility Robotics 的 Digit 是面向仓储与物流应用的双足人形机器人：

- 自 2023 年起在 Amazon 仓库试点部署，用于搬运塑料箱等任务，将物品从传送线转移到货架或其他位置，能在复杂环境中行走和操作。[55–58][61–64]
- Digit 采用统一 autonomy stack，在室内外使用激光雷达、双目摄像头和 GPS，集成定位、建图、路径规划、行为选择和全身控制，实现复杂环境中自主行走；在仓储场景中通过多传感器融合感知货架、托盘和人员，并在长期部署中持续收集数据优化模型。[53–58]
- NVIDIA 案例指出，Agility 使用 Isaac Sim 和 Isaac Lab 搭建大规模仿真环境，训练 Digit 的“whole‑body control foundation model”，并在 GXO 和 Schaeffler 等客户现场部署，形成仿真‑现实闭环。[55–58]

Statesman Journal 报道其在俄勒冈州 Salem 建成针对商用人形机器人的工厂：2024 年工厂开始投产，2025 年已批量生产 Digit，应对仓库劳动力短缺。[61–63] KraneShares 将 Digit 与 Tesla、Figure 一并视为 2026 年“从试点走向平台化商业”的代表。[65][66][72]

### 3.4 Apptronik：Apollo 与大额融资驱动的通用人形

Apptronik 的 Apollo 是设计与人类共享工作空间的通用人形机器人，应用于仓储物流、制造和零售：

- 2023–2024 年公开展示，能执行搬运和抓取任务；截至 2026 年重点从 Demo 走向商业生产，处于前期量产与试点阶段。[61–64]
- Crunchbase News 报道其完成 5.2 亿美元 A 轮扩展融资，用于从小批量原型向更大规模制造过渡，并加强软件和 AI 投入，以提升自主性和多场景适应能力。[61–62]
- QIA 等机构参与此次融资，反映市场看好人形机器人替代重复性体力劳动与实现商业规模部署的潜力。[61–64]

### 3.5 Sanctuary AI：Carbon 认知架构+通用人形 Phoenix

Sanctuary AI 的 Phoenix 被定位为“为工作设计的通用 humanoid 机器人”，由 Carbon 认知架构和软件平台驱动。[39–42][71–75]

- Carbon 将自然语言指令转换为动作，集成语言理解、任务规划和感知；Phoenix 硬件高度人形，配备 20 自由度触觉手、摄像头和力/扭矩传感器，以支持精细操作。[39–42]
- 媒体特写称其目标是在家庭清洁和服务等场景执行广泛任务，成为具有人类般智能的通用机器人之一。[40][41][71–75]

### 3.6 大模型平台与开源生态：DeepMind、OpenAI 等

- Google DeepMind 的 RT‑2 和 RT‑X：RT‑2 将互联网规模 VLM 扩展为 VLA，RT‑X 整合 60 多种机器人平台数据，旨在训练可跨平台迁移的通用机器人模型。[13–18][20–23][69–72]
- Gemini Robotics：Gemini Robotics 1.5 在基础模型之上加强具身推理，将感知、规划、工具使用与动作整合为物理世界 AI agent，支持多种机器人形态；Gemini Robotics On‑Device 支持在边缘设备本地运行，满足低时延与隐私需求。[17][18][36–38]
- LLM 具身综述：Frontiers 综述将基于 LLM 的机器人系统视为 Agentic AI，强调其感知‑规划‑执行结构和相关伦理问题；OpenAI 社区实践表明，开发者广泛使用 GPT‑4 进行任务拆解和高层控制，将语言指令转换为动作序列。[69][70][76][77]

整体来看，美国在“基础模型+通用硬件+资本+生态”维度形成明显领先。

---

## 四、中国具身智能代表性公司与技术路线

### 4.1 华为：Pangu 世界模型与云端 6G 具身架构

华为在具身智能方向主要体现在 Pangu 世界模型与面向 6G 的云端机器人架构：

- 华为官方指出，具身智能是 humanoid 机器人的关键技术，并被写入中国 2025 年政府工作报告；Pangu 模型用于 embodied AI，为 humanoid 机器人提供世界建模与决策能力。[43][44]
- 华为云新闻稿描述，Pangu 世界模型可为智能驾驶和 embodied AI 机器人生成数字物理空间，用于连续训练和复杂场景模拟，提高智能体在真实环境中的性能。[45]
- 华为技术文章提出，利用基础模型统一机器人感知、决策和控制，并构建基于 6G 的云端大模型控制系统，为机器人提供大带宽与低时延连接，使其依托云端基础模型实现更复杂行为。[43–45]

从全球技术路线视角看，华为代表了中国在“世界模型+云端大模型控制”方向的系统布局，与 DeepMind 世界模型和美国厂商的大规模仿真路线形成对标。[8][69–72]

### 4.2 优必选（UBTECH）：Walker 系列与工业应用

优必选在 Walker 系列人形机器人上采取“传统控制+学习增强+大模型融合”的路线：

- Walker X：被描述为高度先进的 AI 机器人，集成六大 AI 技术，搭载升级版基于视觉的导航和手眼协调系统，用于实现复杂任务。[50]
- Walker S：工业应用视频显示，其在传统视觉伺服和柔顺控制基础上，融合强化学习和模仿学习，以提升在工业装配等任务中的鲁棒性和泛化能力。[51]
- Walker S2：MERICS 评论指出其于 2025 年推出，具备 162 度旋转范围以适应装配任务，并采用 dual‑loop AI 系统，以提升任务灵活性和安全性。[52]
- 大模型集成：社区信息称优必选与百度合作，将大型 AI 模型集成到 Walker S 中，使其完成折叠衣物与物品分类等任务；但该信息来自社区帖子，非官方信源，需审慎对待。[50][51]

优必选代表了中国在工业场景人形机器人上的较深入布局。

### 4.3 傅利叶智能（Fourier）：GR‑1 与视觉/运动控制强化

傅利叶智能的 GR‑1：

- 被描述为面向实际应用设计的 humanoid，具备多用途躯体结构和先进运动控制能力，可复制人类动作。[48]
- 新闻稿称 GR‑1 采用新的高级视觉感知方案，被描述为首个采用该方案的 humanoid，以提升环境感知精度与鲁棒性，具体算法和硬件细节未详。[49]

整体信息偏重硬件与感知能力，控制架构细节披露有限。

### 4.4 西湖心辰/Westlake Robotics：GAE 动作基础模型与 Titan O1

西湖心辰旗下 Westlake Robotics 发布 Titan O1：

- 由自研 General Action Expert（GAE）驱动，GAE 被描述为通用动作基础模型，可模仿人类行为并在不同场景中执行任务，支持一个人同时操作多台机器人；单一模型可以在多机器人实例上运行。[46][47]
- 媒体报道强调，GAE 为 Titan O1 提供跨场景通用任务能力，体现多机器人多任务能力。[46][47]

从技术路线看，GAE 与 RT‑X、Redwood 等类似，属于“动作基础模型 / VLA”方向，但更强调多机器人多实例部署。

### 4.5 中国技术路线小结

- 在“世界模型+云端基础模型”方向，华为 Pangu 与 6G 架构体现了将世界模型用于数字物理空间生成与云端控制的系统思路。[43–45][69–72]
- 在“人形+工业场景”方向，优必选、傅利叶与西湖心辰分别从控制强化、视觉感知优化与动作基础模型切入，强调工业装配与通用任务能力。[48–52]
- 相比美国，公开资料中中国公司在人形机器人商业部署规模、典型客户与融资金额披露较少，本报告无法给出与 Figure/Apptronik 同级别的融资对比结论。

---

## 五、欧洲具身智能代表性公司与技术路线

### 5.1 ANYbotics：ANYmal 与复杂地形自治巡检

ANYbotics 的 ANYmal 是欧洲腿式机器人代表：

- 软件栈采用开放架构，涵盖运动控制、定位与建图、导航等完整功能，并为研究和学术合作提供 API 和开发环境，以实现自定义感知和控制算法。[53][73–75]
- ANYmal 集成激光雷达和摄像头等多种传感器以及高级状态估计算法，使其能在复杂地形上自主行走；被定位为适用于苛刻工业环境的自治巡检解决方案。[53–55][73–75]

ANYmal 体现出“传统分层自治栈+多传感器+开放平台”的典型欧洲路线，更注重可靠性、工程完备性与研究生态。

### 5.2 Boston Dynamics：Atlas/Spot 与工业级高动态控制

Boston Dynamics 在全球广泛部署，其技术路线在欧洲工业与研究社区亦被广泛采用：

- Atlas：被定位为面向现实工业工作、物料搬运和智能自动化的高动态人形平台，具备在复杂环境中执行跳跃、翻转等高自由度动作的能力。[56][57]
- 软件平台：Atlas、Spot 与 Stretch 在软件层共享模块化运动生成与基于行为树的任务控制平台，通过多模态传感器构建环境模型，使机器人适应不同地面和障碍，实现任务自适应。[56–58]
- 演进路径：从运动研究平台向工业版过渡，体现从实验室 Demo 向工业应用演进的路线。[56–58]

鉴于其业务全球化，本报告在技术对比中将其作为“传统分层+高动态控制”路线的典型案例。

---

## 六、全球融资与资本动向（2022–2026）

综合行业研究与新闻报道，2023–2026 年通用人形与具身机器人融资显著升温：

- Figure AI：2024 年完成约 6.75 亿美元融资，投资者包括 OpenAI、微软、英伟达和 Jeff Bezos 等，资金用于建设人形机器人生产线并推进量产与商业化试点。[29–31]
- Apptronik：完成 5.2 亿美元 A 轮扩展融资，QIA 等机构参与，旨在将 Apollo 从小批量原型推向前期量产和试点部署。[61–64]
- 行业整体：Robozaps 与 KraneShares 研究将 Tesla、Figure、Agility、Apptronik 等视为 2025–2026 年人形机器人领域的关键参与者，普遍处于“从试点部署向早期平台化商业化过渡阶段”。[60][65][66][72]

Omdia 市场雷达报告指出，通用具身智能机器人市场涵盖人形与非人形形态，应用于工业、物流和服务等领域，反映资本对“通用具身机器人”这一新兴赛道的结构性看好。[59][60]

由于中国与欧洲公司融资数据披露有限，本报告在区域对比层面更侧重技术与产品维度，对融资规模仅在个案层面进行引用。

---

## 七、团队与人才流动特征

- 创始人背景：Figure AI 创始人 Brett Adcock 曾是 Archer Aviation 联合创始人，具备深度硬件与新兴产业创业经验，反映美国具身智能公司创始人与核心团队往往来自自动驾驶、航空航天和高性能硬件领域。[32]
- 大模型与机器人交叉：ELLMER、Gemini Robotics 与多家机器人公司合作案例表明，大模型研究团队与机器人团队的深度协同正在成为关键能力。[33–38][36–38][69][70]
- 区域人才生态：
  - 美国：以 Tesla、Figure、Agility、Apptronik 和 DeepMind/Google 为核心，集聚 AI 大模型、机器人控制和硬件制造多专业人才。[19–22][25–31][33–38][61–66]
  - 中国：华为云与 Pangu 团队在世界模型与云端基础设施方面积累深厚，优必选、傅利叶与 Westlake 团队在机器人本体与控制方面深耕；政策层面将具身智能写入政府工作报告，有望长期吸引人才与资本。[43–48][49–52]
  - 欧洲：ANYbotics 与学术机构合作紧密，ANYmal 的开放 API 与研究合作项目显示欧洲在腿式机器人基础研究与工程化之间具有良好桥梁。[53–55][73–75]

现有证据未系统披露各公司 CTO、首席科学家及其详细履历，仅能从个别案例与合作关系侧面观察人才流动。

---

## 八、投资视角的机会与风险

### 8.1 投资机会

1. **端到端 VLA / 动作基础模型+通用人形平台**

   - 代表：Figure Helix+Figure 03、1X Redwood+NEO、Westlake GAE+Titan O1、RT‑2/RT‑X 在多平台上的应用。[13–18][19–22][24–28][46–48][69–72]
   - 投资逻辑：单一大模型统一多机器人、多任务能力，可在制造、物流和服务领域大规模复制，具备平台化潜力。Figure 与 Apptronik 的大额融资与工厂建设，反映资本对“通用人形劳动力”赛道的看好。[29–31][61–64][65][66][72]

2. **具身 LLM+分层控制与 Agentic AI 平台**

   - 代表：ELLMER、Sanctuary Carbon、Gemini Robotics 系列、基于 GPT‑4 的 Agentic 系统。[33–42][36–38][69][70][76][77]
   - 投资逻辑：通过 LLM 承担高层任务理解与规划，可快速复用现有大模型能力与工具链，在家庭服务、实验室助手等场景展现高灵活性，并具备工具链与 SaaS 化潜力。[33–38][69][70][76][77]

3. **世界模型+仿真基础设施**

   - 代表：华为 Pangu 世界模型与 6G 云端控制、Agility+NVIDIA Isaac 仿真、DeepMind 世界模型研究等。[8][43–45][55–58][69–72]
   - 投资逻辑：世界模型为具身智能提供高样本效率和强泛化能力，是长周期技术底座；仿真平台与世界模型可向多家机器人厂商输出“训练即服务”，具备技术中台价值。

4. **高可靠腿式/巡检平台与开放软件栈**

   - 代表：ANYmal、Boston Dynamics Atlas/Spot 软件栈。[53–58][73–75]
   - 投资逻辑：在能源、化工和基础设施巡检等高风险场景，对安全性和可靠性的要求远高于通用人形，对价格敏感度相对较低；开放软件栈与 API 有利于生态扩展。

### 8.2 关键风险与不确定性

1. **技术成熟度与安全**

   - 端到端大模型控制在新任务泛化方面表现突出，但高度依赖大规模数据与算力，且可解释性和安全对齐问题凸显。[7][11][13–18]
   - LLM 控制具身代理被视为 Agentic AI，需要面对伦理与安全监管问题，尤其在现实世界高自主行动时。[69][70]

2. **商业化节奏与成本**

   - Tesla Optimus、Figure 03 和 Apollo 等产品普遍仍处于内部试点或前期量产阶段，目标价格与当前成本之间存在差距；研究指出 2026 年仍是“从试点到平台化”的过渡节点，而非全面规模化。[35–38][60][65][66][72]
   - 订单规模和客户结构尚未公开透明，收入和毛利率缺乏长期验证。

3. **竞争格局与路径依赖**

   - 美国基础模型厂商在 VLA、ELLMER、Gemini Robotics 等方向上先发，可能锁定具身智能上层协议与开发工具链。[13–18][33–38][36–38][76][77]
   - 中国与欧洲厂商在世界模型、工业巡检等细分领域具有优势，但在通用人形平台与全球开发者生态上尚处追赶阶段。[43–45][47–52][53–60]

4. **政策与伦理**

   - 华为提到具身智能已写入中国 2025 年政府工作报告，反映监管关注度提高；欧美在 Agentic AI 伦理与安全上也有持续讨论，这可能在未来形成合规成本和市场准入变量。[43][44][69][70]

---

## 结论

2022–2026 年是具身智能从“任务级机器人”迈向“通用具身平台”的关键窗口期。技术上，四大路线——端到端 VLA / 动作基础模型、具身 LLM+分层控制、世界模型+规划控制、传统分层自治栈+学习增强——在 ABC 框架下逐步融合，多模态大模型与世界模型成为核心支柱。[1–12][69–72]

区域对比上：

- **美国**：通过 Tesla、Figure、Agility、Apptronik、Sanctuary 等通用人形平台，以及 RT‑2、Gemini Robotics、ELLMER 等具身大模型平台，在技术、资本与生态上形成综合领先，并已在工厂和仓储实现早期部署与批量试点。[19–22][25–31][33–42][55–58][61–66][69–72]
- **中国**：通过华为 Pangu 世界模型与 6G 云端控制在世界模型和数字物理空间构建方面突出，优必选、傅利叶、西湖心辰在面向工业应用的人形机器人和动作基础模型上布局；政策层面的牵引为中长期发展提供支撑，但公开信息中商业部署和融资规模仍相对有限。[43–52]
- **欧洲**：以 ANYmal 等腿式平台和 Boston Dynamics 软件栈为代表，更强调高可靠、工程完备与开放研究生态，为工业巡检和复杂地形应用提供成熟方案。[53–60][73–75]

对于投资机构而言，短中期可重点关注：1）已经迈入产线与仓储早期部署、具备大模型协同能力的通用人形平台；2）能够输出世界模型与仿真基础设施、服务多机器人厂商的技术中台；3）在高风险巡检与特殊环境中具备明显可靠性优势的腿式平台。同时需谨慎评估技术成熟度、成本曲线与安全/伦理监管带来的不确定性。

---

## 参考文献

[1] Aligning Cyber Space with Physical World: A Comprehensive Survey on Embodied AI.  
[2] 同上（ABC 框架与具身系统组成描述）。  
[3] 同上（Embodied perception / interaction / agent / sim‑to‑real 四大研究目标）。  
[4] 同上（Multi‑modal Large Models 和 World Models 在具身 AI 中的作用）。  
[5] Paper List and Resource Repository for Embodied AI.  
[6] Large Model Empowered Embodied AI: A Survey on Decision …  
[7] 分析节点：全球具身智能四大技术路线归纳。  
[8] Embodied World Models for Decision Making.  
[9] A Survey of Embodied World Models.  
[10] Embodied AI: From LLMs to World Models [Feature].  
[11] Agentic LLM-based robotic systems for real-world applications: a review on their agenticness and ethics.  
[12] Robotics and AI: An AI Atlas Report | Emerge Haus Blog.  

[13] RT-2: Vision-Language-Action Models.  
[14] RT-2: New model translates vision and language into action.  
[15] RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control.  
[16] General-Purpose Robot RT-X: A Collaboration between DeepMind and 33 Academic Labs.  
[17] Gemini Robotics 1.5 brings AI agents into the physical world.  
[18] Gemini Robotics On-Device brings AI to local robotic devices.  

[19] Project Go-Big: Internet-Scale Humanoid Pretraining and …  
[20] Helix: A Vision-Language-Action Model for Generalist Humanoid …  
[21] From Concept to Production: Humanoid Robotics at Scale.  
[22] Ramping Figure 03 Production.  

[23] Redwood AI - 1x Tech.  
[24] 1X’s NEO humanoid gains autonomy with new Redwood AI model.  
[25] 1X Business Breakdown & Founding Story - Contrary Research.  

[26] AI & Robotics | Tesla.  
[27] Tesla’s Shift to End-To-End Deep Learning: Full Breakdown.  
[28] Transitioning from Rule-Based Driving to Large Driving Models.  

[29] Figure AI raises $675M to commercialize humanoids.  
[30] Figure AI’s humanoid robot reaches its first customer.  
[31] Humanoid robot-maker Figure partners with OpenAI and gets backing from Jeff Bezos and tech giants.  

[32] What Is Figure AI?  
[33] Embodied large language models enable robots to complete complex tasks in unpredictable environments.  
[34] From text to motion: grounding GPT-4 in a humanoid robot “Alter3”.  

[35] Tesla’s Robot, Optimus: Everything We Know.  
[36] Tesla Optimus Gen 2 Review: Specs, Price, Factory Use [2026].  
[37] Tesla Optimus vs Unitree G1: Full 2026 Comparison.  

[38] Robotics in the Age of Generative AI.  

[39] Sanctuary AI Unveils Phoenix™ - A Humanoid General-Purpose Robot Designed for Work.  
[40] Sanctuary AI Phoenix Review [2026].  
[41] Hello, I’m Phoenix. Would You Like Your House Cleaned?  

[42] 30+ Humanoid Robot Companies Ranked [2026].  

[43] #Pangu model for embodied AI sounds cool, but what can it actually …  
[44] Huawei Cloud Announces Pangu Models 5.5 and All-new AI Cloud …  
[45] Robots Empowered by AI Foundation Models and the Opportunities …  

[46] Chinese company unveils humanoid robot powered by general action expert model (Westlake University/Westlake Robotics).  
[47] 同上（WIC Internet 报道）。  

[48] Fourier GR-1 - FOURIER-Robotics.  
[49] Fourier Unveils GR-1’s Breakthrough in Vision Technology for …  

[50] UBTECH Walker X Commercial Humanoid Robot.  
[51] UBTECH Humanoid Robot Walker S: Industrial Application Ability.  
[52] UBTech: Humanoid robots for the future of manufacturing.  

[53] Advance Robotics Research with ANYmal.  
[54] ANYmal: the cutting-edge path to advance robotics research.  
[55] ANYmal - Autonomous Robotic Inspection Solution.  

[56] Atlas Humanoid Robot.  
[57] Atlas’ Evolution From Research Robot to Industrial Humanoid.  
[58] Perception and Adaptability (Atlas 视频等）。  

[59] Omdia Market Radar: General-purpose Embodied Intelligent Robots, 2026.  
[60] Humanoid Robotics In 2026: The Race From Pilot To Platform.  

[61] Amid Record Robotics Funding, Apptronik Raises $520M Series A Extension.  
[62] QIA Joins $520m Apptronik Round as Humanoid Robotics Move Toward Commercial Scale.  

[63] How Agility Robotics factory in Salem is building the robot revolution with Digit.  
[64] Amazon announces 2 new ways it's using robots to assist employees and deliver for customers.  

[65] Figure AI: Bringing Humanoid Robots Into Industry.  
[66] Robozaps: 多篇关于 Tesla Optimus、Unitree G1、Figure 等的行业分析与评测。  

[67] Robotics and AI: An AI Atlas Report | Emerge Haus Blog.  
[68] Humanoid robot-maker Figure partners with OpenAI …（同文 [31]）。  

[69] Embodied large language models enable robots to complete complex tasks in unpredictable environments.  
[70] Agentic LLM-based robotic systems for real-world applications: a review on their agenticness and ethics.  

[71] What Is a Humanoid Robot? [2026].  
[72] 30+ Humanoid Robot Companies Ranked [2026].  

[73] ANYmal research & academia 合作项目资料。  
[74] ANYmal - Autonomous Robotic Inspection Solution（同 [55]）。  
[75] Atlas-related Boston Dynamics materials（同 [56–58]）。  

[76] Robotics in the Age of Generative AI（OpenAI 社区）。  
[77] Alter3 / ELLMER 相关论文与资料（见 [33–34]）。