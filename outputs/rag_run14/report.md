## 2022-2026 年全球具身智能技术路线与代表性公司分析  
（技术路径、产品与商业化进度、融资与团队画像）

---

## 引言：具身智能的定义、研究范围与核心结论

具身智能通常指能够在物理世界中感知、理解并执行动作的智能系统，典型形态包括人形机器人、移动操作平台、仓储物流机器人以及各类服务机器人。2022-2026 年间，多模态大模型与机器人控制技术的结合，使具身智能从以感知为主的“感知型智能”演进为可在复杂环境中执行任务的“交互型智能”，体现在 VLA（Vision-Language-Action）模型、强化学习、模仿学习和世界模型等多条路线的快速发展。[1][2][3]

本报告聚焦 2022-2026 年全球具身智能的发展，围绕以下几个维度展开：

- 技术路线：VLA/机器人基础模型、端到端强化学习、模仿学习、世界模型及混合架构。[4][5][6]
- 代表性公司：Figure AI、Tesla Optimus、Boston Dynamics、Agility Robotics、Sanctuary AI、1X Technologies 及 UBTECH（优必选）、宇树等中国企业的技术路径与产品布局。[7][8][9][10][11][12]
- 产品与商业化：人形机器人、仓储物流机器人、家用/服务机器人等场景的 Demo、试点到商业化部署过程。[13][14][15]
- 融资与资本格局：围绕机器人基础模型与通用人形机器人，公司层面的融资规模与资本关注点。[16]
- 团队与人才：核心团队教育与产业背景、技术架构与组织结构之间的匹配。[7][17]
- 投资视角：不同路线在数据需求、泛化能力、落地场景和资本密度上的差异与风险。

从图谱证据可归纳出几个关键结论与投资要点：

1. **VLA 与机器人基础模型成为具身智能的主干路线之一**。多项综述与行业报道将 VLA 模型视为新一代具身智能核心技术，能够统一视觉、语言与动作，实现从指令到动作的端到端映射，并在家用、移动机器人场景中展现出较强的泛化能力。[4][18][19][20]
2. **端到端强化学习和模仿学习在特定任务上仍具优势，但面临样本效率与安全性瓶颈**。实际机器人部署中，端到端 RL 在高性能控制任务（如四旋翼飞行）上表现突出，而模仿学习及其增强形式在接触丰富的操作任务中被广泛采用。[21][22][23][24][25]
3. **世界模型与混合架构受学术与产业共同看好，被视为向“通用机器人”过渡的关键组件**。世界模型能够减少真实数据需求并提升长时规划能力，业界分析认为其有望解锁更通用的机器人能力。[26][27][28][29]
4. **代表性公司在技术栈上呈现分层混合趋势**：  
   - Figure 与 Helix：VLA 基础模型 + 全身控制；[8][30]  
   - Tesla Optimus：多模态 foundation model 感知 + 端到端强化/模仿学习策略；[31][32]  
   - Agility Digit：基于 NVIDIA 平台的全身控制 foundation model；[33]  
   - Sanctuary Phoenix：Carbon 高层认知体系 + 深度学习与强化学习技能模块；[34][35]  
   - 1X NEO：面向家庭的 Generalist AI/Redwood 模型驱动；[36][37]  
   - UBTECH、宇树等：在步态控制、平衡控制与 RL/模仿等路线结合上发力。[10][38][39]
5. **商业落地从仓储物流与工业场景率先破局**。Digit 在 GXO、Schaeffler 等客户处进入试点；Phoenix 在零售及仓储执行点货、搬运和终端操作；部分中国企业在人形及服务机器人领域实现多台、多场景协同实训。[13][14][15][40]
6. **资本关注聚焦“机器人基础模型 + 通用人形平台”**。以 Physical Intelligence 等为代表的公司被报道融资规模约数亿美元，用于构建通用机器人基础模型及配套云训练基础设施。[16]
7. **人才与组织上，“基础模型 + 具身控制”路线高度集中在具备大模型和机器人双重经验的团队**，创始和核心成员来自 Boston Dynamics、Tesla、Apple 等公司或顶级学术机构。[7]

本报告所有事实性陈述均以图谱证据为基础；对部分存在口径差异的估值、产量等数据，本报告不做具体数字复述，仅以区间或定性方式概括，并在相关章节中标注其局限。

---

## 第一章 技术路线全景：VLA、RL、模仿学习、世界模型与混合架构

### 1.1 具身智能主干技术路线概览

多篇综述指出，在多模态大模型时代的具身智能中，VLA 模型、强化学习、模仿学习与世界模型构成 2022-2025 年的主要方法学路线。[4][41] 这些路线的核心特征如下：

- **VLA 模型/机器人基础模型**：统一视觉、语言与动作，通过大规模预训练结合机器人数据，实现从环境感知与指令理解到动作输出的端到端控制。[18][42][43]
- **强化学习（RL）**：涵盖 model-free、model-based 和 offline RL 等类别，被用于端到端导航、操作和高性能控制任务。[21][44][45][46][47]
- **模仿学习（IL）**：包括行为克隆、逆强化学习、对抗模仿等，尤其在接触丰富的复杂操作任务中广泛应用。[23][24][48][49]
- **世界模型（World Models）**：面向环境结构理解和未来状态预测，为模型式 RL 和长时规划提供基于模拟的“世界”。[26][27][50][51][52]
- **混合/分层架构**：将 VLA 或大模型与传统控制、世界模型或符号规划结合，形成高层策略与低层控制分层的系统。[53][54][55]

各路线具有不同优势与瓶颈，且在近年来呈现出明显的融合趋势。

### 1.2 VLA 模型与机器人基础模型

#### 1.2.1 VLA 模型的定义与特点

VLA 模型是一类同时处理视觉输入、语言指令与动作输出的模型，被视为具身智能中的新型端到端控制范式。[18][56] 综述与期刊文章将其定义为：

- 将视觉感知、语言理解与控制统一在一个端到端系统中。[18][42]
- 对比传统流水线（感知、规划、控制分离），VLA 简化了任务指定与行为生成过程，有利于适应复杂和开放环境。[42]

VLA 模型通常采用以下训练范式：

- **大规模预训练 + 机器人数据微调**：结合网络规模数据（图像、视频、文本）与机器人轨迹，提高泛化能力与数据效率。[19][20][43]
- 典型代表包括 RT 系列（RT-1、RT-2）等，将视觉和文本映射为低层行动序列。[18][57][58]

VLA 模型在家用服务机器人、移动机器人等领域展现出应用潜力，但也存在高数据需求和可解释性不足等问题。[19][42]

#### 1.2.2 代表性模型与演进

- **RT 系列（RT-1、RT-2）**：被多篇文献视为代表性 VLA 模型，主要面向机器人操作和导航任务。[18][57]
  - RT-2 通过结合 web 规模多模态数据与机器人数据，直接将视觉与文本映射为低层控制指令，具备将 web 知识迁移到现实任务的能力。[57][58][59]
  - 同期的学术研究（包括发表于 2025 年的期刊文章）表明，相比窄域基线，预训练的 VLA 模型在复杂任务与泛化能力上具有显著优势。[59][60]
- **DeMaVLA、RoboMamba 等**：面向家用和高效操作场景的 VLA 基础模型：
  - DeMaVLA 定位为家用机器人 VLA 基础模型，强调跨任务、跨场景可复用技能。[61]
  - RoboMamba 强调在保持多模态感知与控制能力的同时降低推理成本，便于在资源受限的机器人平台部署。[62]
- **其他基础模型与比较**：
  - OpenVLA、π0、MolmoAct 2 等机器人基础模型在 2025 年左右被技术博客系统比较，维度包括数据规模、模型架构、开放性和部署模式。[20]
  - π0.7 被报道在组合泛化方面具有“无需任务特定训练的组合执行能力”，能够对组合命令执行新任务。[63]

此外，NVIDIA 的 GR00T N1 被描述为“通用于人形机器人的开放基础模型”，强调通过大规模多源数据预训练支持多任务、多环境控制，并在学术报告中演示 sim-to-real 与类人推理能力。[64][65]

#### 1.2.3 VLA 与机器人基础模型的挑战

针对 VLA 模型，研究社区指出其在以下方面仍存在挑战：

- 长时任务与多步规划能力不足，难以稳定处理复杂任务链。[21][66]
- 解释性、数据偏差和安全问题尚未得到充分解决。[66]
- 产业文章提出“VLA 将成为通用机器人基础的下一步”，但实际部署仍处早期，需要在安全性和可靠性方面进一步工程化。[19][66]

### 1.3 强化学习：端到端、离线与人类反馈

#### 1.3.1 RL 在机器人中的应用与挑战

强化学习已被用于实际机器人中的端到端视觉导航与操作。然而，综述指出，实际部署仍高度受限于样本效率和安全性。[21][44]

- RL 在现实机器人中广泛用于视觉导航和操作任务，但需要大量试错数据。[21]
- 安全性和稳定性是主要瓶颈，尤其是在复杂工业环境中。[21][44]

#### 1.3.2 RL 类型与新范式

- **Model-free、Model-based、Offline RL**：  
  - RL 可按是否显式建模环境分为 model-free 与 model-based；再按数据来源区分 online vs offline。[44][45]
  - Offline RL 利用固定的机器人数据集（例如 conservative Q-learning），在不进行在线交互的情况下训练策略，提高安全性与可控性。[46][47]
- **高性能控制案例**：  
  - 在四旋翼时间最优飞行任务中，端到端 RL 被证明可实现接近时间最优的高度激进轨迹，并与传统控制及行为克隆进行对比，展示 RL 在极限性能上的优势。[22][47]
- **联合在线-离线框架**：  
  - Uni-O4 等方法提出统一在线和离线 RL 的框架，利用日志数据与在线交互共同训练，被证明在真实机器人上相较纯在线或纯离线方案表现更好。[48]
- **RLHF 在机器人中的潜力**：  
  - RLHF 标准管线包括：收集人类偏好数据、训练奖励模型、通过 RL 优化策略。[49][50]
  - 文献指出 RLHF 虽在语言模型中最为成熟，但概念上可扩展到机器人与控制任务，在具身环境中通过人类偏好引导策略学习。[49][50][51]

### 1.4 模仿学习：接触丰富任务与交互式学习

从 2022 到 2025 年，模仿学习在接触丰富的复杂操作任务中应用广泛，包括行为克隆、逆强化学习与对抗模仿（如 GAIL）。[23][24]

- 多篇综述统计了 peg 插入、工具使用等操作任务中模仿学习的实践，说明在高精度接触任务中，模仿路线是重要选项。[23]
- 交互式模仿学习通过在线纠正与反馈提升样本效率和最终性能。实验证明，其在灵巧操作任务中相比纯离线模仿与纯 RL 具有更好样本效率与性能。[24]

此外，研究提出通过估计示教者的专业水平，对多源示教数据进行加权或过滤，以提升从异质人类示教中学习的效果。[52]

### 1.5 世界模型：环境理解与长时规划

#### 1.5.1 世界模型的类型与功能

世界模型被综述为主要服务于两类目标：[26][27]

- **理解环境结构**：如三维场景建模，提供更丰富的环境表征。
- **预测未来状态**：如视频预测与物理建模，为行动规划提供前瞻信息。

在具身智能中，世界模型支持：

- 三维场景理解和视频预测，为机器人提供环境和未来状态的估计。[26]
- 模型式 RL 中的模拟，减少真实交互需求。[27][51]

#### 1.5.2 具身世界模型与物理约束

专门针对具身世界模型的综述指出，世界模型是具身 AI 中决策与模型式 RL 的核心组件，与 VLA 等直接策略方法形成互补。[27]

- RoboScape 等物理约束世界模型通过将物理规律嵌入潜在动力模型，提高模拟可靠性，并在机器人规划和策略学习中提供高保真虚拟环境。[28]

#### 1.5.3 视频世界模型与产业视角

- 技术博客指出，视频世界模型从单纯的视频生成发展为捕捉物理动力的能力，被视为通向可用于具身推理的世界模型的一步。[29]
- 风险投资机构分析认为，世界模型可以显著降低机器人对真实数据的需求，并通过长时规划解锁更多通用任务能力，因此被视为“解锁通用机器人”的重要方向。[51]

### 1.6 混合与分层架构：VLA + 世界模型 + 传统控制

多项研究与产业案例表明，实际系统往往采用混合和分层架构：

- **高层 VLA / 多模态模型 + 低层动态控制**：  
  - DAM-VLA 将高层 VLA 用于视觉和语言理解，低层动态动作模型用于连续控制，实现感知-决策与动力控制的分离。[53]
  - 知识隔离 VLA 在 VLA 周围或内部插入安全约束与知识模块，将安全规则与 VLA 能力结合。[54]
- **VLA / 多模态感知 + 大语言模型规划**：  
  - VLaser、Embodied-R1 等混合模型将多模态感知与显式大语言模型规划结合，构成“感知 + 语言推理 + 控制”的组合架构。[55]
- **工业级混合系统**：  
  - Sanctuary 的 Carbon 架构结合深度学习、强化学习与符号规划；Figure 的 Helix 与 whole-body control 组合，均体现高层认知/策略与低层控制分层的设计。[34][35][30][67]

这些混合路线为后续代表性公司技术路径提供了重要参考。

---

## 第二章 代表性公司与技术路径

本章围绕主要人形与具身智能公司，分析其技术架构与应用场景。限于图谱证据，本章不对每家公司的完整技术细节做超出公开材料的推断。

### 2.1 Figure AI：Helix VLA + Figure 03 通用人形平台

Figure 将自己定位为“AI-first 的通用人形机器人公司”，目标是在工业、商业和日常环境中部署 Figure 01/02/03 等代际人形平台。[7]

#### 2.1.1 技术路径与架构

- Figure 官网强调“AI-first”技术路径，依托大规模神经网络、强化学习、仿真训练等技术栈。[7]
- 技术与招聘信息显示 Figure 将具身智能能力拆分为感知、全身控制（whole-body control）、规划与操作等模块。[7]
- Figure 03 新闻稿指出，该代平台面向物流、制造和家庭场景，强调通过视觉与其他传感器实现感知与导航，并可在仓库与生产线 24/7 运行。[8]
- 图谱中提到 Figure 03 与 Helix VLA 模型“深度集成”，Figure 03 具备高自由度手部及全身控制，以执行 Helix 输出的通用操作命令，支持未显式编程的多种任务。[30]

在系统架构层面，分析节点指出：

- Figure 采用 VLA 基础模型（Helix）提供高层任务规划和操作序列，结合全身控制器执行多关节动作，是一种“VLA + 分层控制”的混合方案。[67]

#### 2.1.2 产品形态与应用场景

- Figure 03 被定位为“通用人形平台”，面向物流、制造与家庭场景。公开材料提到其在复杂环境中执行物体抓取和操作任务，以及在仓库/生产线中持续运行。[8]
- Figure 官方强调 Figure 03 面向“Helix、家庭与全球大规模部署”，表明其目标客户包括工业客户与家庭用户。[8][30]

### 2.2 Tesla Optimus：多模态 Foundation Model + 端到端 RL/IL

#### 2.2.1 多模态基础模型与端到端学习

- Tesla 在 Optimus 项目中招聘“AI Engineer, Vision & Foundation Models”等岗位，明确提出为 Optimus 构建视觉与多模态 foundation models，用于环境感知、任务理解和行为生成，以解决稳健具身智能问题。[31]
- 另一职位“Reinforcement Learning Engineer, Policy, Optimus”描述，岗位负责开发端到端机器人学习策略，采用强化学习或模仿学习，从传感器输入到控制输出训练策略，通过奖励正确动作及惩罚错误动作塑造行为。[32]

据此可见，Optimus 技术路线组合包括：

- 多模态基础模型用于感知和任务理解；[31][68]
- 端到端强化学习与模仿学习用作策略学习，从感知输入到控制输出形成闭环。[32]

#### 2.2.2 应用场景与产品定位

- Tesla 官方 AI 页面（图谱中收录）强调其在自动驾驶与机器人领域追求具身智能，但具体 Optimus 部署场景在图谱中未给出详细客户或场景，只能确认其目标是稳健的人形具身智能系统。[31]

### 2.3 Boston Dynamics：Atlas 与工业级全身控制

#### 2.3.1 Atlas 技术路径与控制策略

- Atlas 产品页面将其描述为企业级人形机器人，用于真实工业环境中的物料搬运和智能自动化。[9]
- Atlas 强调 dynamic whole-body control，可在复杂环境中完成抓取、搬运与行走任务，依托先进的感知与运动规划理解环境并规划路径与动作。[9]
- Boston Dynamics 博客指出最新一代电驱 Atlas 具备更高力量密度与灵活性，并采用动态平衡与全身协调控制策略以适应高强度工业任务。[69]

这些声明表明，Atlas 技术路线侧重：

- 高性能动态平衡控制和全身协调控制；
- 结合高级感知与运动规划，而非明确采用 VLA 或基础模型架构（公开材料未说明）。

#### 2.3.2 产品线与系统组合

Boston Dynamics 将 Spot（四足）、Stretch（物流码垛）与 Atlas 列为互补产品，从检测到搬运与复杂操作形成完整方案，Atlas 中心定位于高强度工业任务中的物料搬运与生产线升级。[69]

### 2.4 Agility Robotics：Digit 与全身控制基础模型

#### 2.4.1 Digit 产品定位与软件平台

- Agility 的 Humanoid Solutions 页面将 Digit 定位为在“人类空间”工作的 humanoid，主要面向物流、仓储与制造中的物料搬运及“连接自动化孤岛”。[11]
- Arc 控制平台提供任务编排与车队管理，使 Digit 能在现有设施中工作，并与人类工人协同，减少基础设施改造需求。[11]

#### 2.4.2 技术路径：Whole-Body Control Foundation Model

- Agility 公告指出 Digit 在 GXO 和 Schaeffler 等客户场景试点部署，用于箱件搬运与托盘化任务，并强调 Digit 已从研究阶段走向商业化部署，被称为“市场领先人形机器人”。[13]
- NVIDIA 案例将 Digit 的控制架构称为“Whole-Body Control Foundation Model”，描述 Agility 使用 Isaac Sim 和 Isaac Lab，在 GPU 上对 Digit 进行大规模仿真训练，形成统一的全身动作生成模型，再部署到实体机器人完成复杂动态任务。[33]

这表明 Digit 技术路线为：

- 基于 NVIDIA 平台的全身控制基础模型；
- 依托大规模仿真训练与 sim-to-real 转移；
- 与 Arc 平台结合实现任务级编排与车队管理。

### 2.5 Sanctuary AI：Phoenix 与 Carbon 混合认知架构

#### 2.5.1 Carbon 架构与技术路线

- Sanctuary 发布 Phoenix 时指出，该机器人由 Carbon AI 控制系统驱动，Carbon 负责视觉、语音、触觉感知、任务理解与动作控制，是 Phoenix 的“脑”。[14][34]
- Phoenix 官方描述其为通用人形机器人，可在为人类设计的环境中完成多种工作任务，包括零售和仓储中的点货、搬运和终端操作。[14][34]
- 另一篇博客详细描述 Carbon 架构由感知、认知和控制模块构成，将深度学习和强化学习等现代 AI 方法与符号任务规划和知识表示结合，目标是赋予 Phoenix 类人智能与广泛任务能力。[35]

分析节点指出：

- Carbon 将高层认知与低层 RL 技能模块结合，是典型高层认知 + 低层学习技能的混合架构。[35][67]
- 与 Figure 的 Helix+whole-body control 方案相比，Carbon 更强调符号任务规划与知识表示，而 Helix 更偏向 VLA 与基础模型。[67]

#### 2.5.2 产品进度与场景

- Sanctuary 报道 Phoenix 已在零售与仓储环境中完成多种任务，包括点货、物料搬运与操作终端设备，作为通用工作机器人的应用示例。[14]
- Phoenix 第七代改进中，官方强调其关节活动范围更接近人类、系统可用性与可靠性提升，并在视觉和触觉感知方面显著增强，以支持更复杂的操作任务。[40]

### 2.6 1X Technologies：Generalist AI 与家用 NEO

#### 2.6.1 公司定位与产品线

- 1X 官方主页将公司定位为总部位于帕洛阿尔托的 AI 与机器人公司，目标是打造能够安全完成家务并提供个性化助理服务的 humanoid 机器人。[36]
- 1X 产品线包括：
  - EVE：早期形式为双轮或移动平台搭配机械臂，面向服务场景；
  - NEO：新一代更完整的人形或类人上半身机器人，定位家用。[36]

#### 2.6.2 技术路径：Generalist AI 与 Redwood 模型

- 1X 官网强调通过 Generalist AI 模型实现任务学习和个性化助手功能。[36]
- NEO 产品页指出 NEO 使用 Redwood AI，即 1X 的通用 AI 模型，用于学习并重复执行家庭任务。NEO 出厂具备基础自主能力，并通过更新与学习逐步增强，其应用场景包括家务辅助、陪伴看护和家庭安全。[37]

此外，1X 官方博客介绍其 World Model 方案，强调从视频到动作的自学习方式，表明公司在世界模型与通用基础模型方向投入。[70]

### 2.7 中国企业：优必选（UBTECH）、宇树与其他本土公司

#### 2.7.1 UBTECH：Walker 人形平台与多场景解决方案

- UBTECH 英文官网展示其提供教育机器人、服务机器人、商用/安防机器人以及 Walker 系列人形机器人，强调 Walker 在步态控制、平衡与环境感知方面的能力。[10]
- UBTECH 将这些能力应用于 AI 教育、安防巡检和智能制造解决方案，显示其技术路线兼顾人形控制与行业解决方案。[10]
- 其他新闻源（图谱中列出）提到 UBTECH 的人形机器人实现多台、多场景、多任务协同实训，并开发多模态大模型 Thinker，但具体技术细节与数值在图谱内仅限于案例层次；本报告不进一步推断其内部模型架构。[41]

#### 2.7.2 宇树与国内人形/四足平台

- 图谱中收录 Unitree 官方开源页面和 GitHub 资源，表明宇树提供部分控制软件与示例代码；另有论文《Reinforcement Learning for H1-2 robot》《Learning Getting-Up Policies for Real-World Humanoid Robots》聚焦在 H1 系列机器人上利用强化学习学习起身策略等技能。[38][39]
- 中国媒体报道指出，宇树与国内其他人形公司在步态控制与学习框架方面形成一定竞争格局，但该类报道主要为行业新闻，并未给出详细控制架构。

#### 2.7.3 其他本土公司

- 图谱中还包含关于智元等公司的新闻资料，指出其在人形机器人学习框架上取得进展，使机器人在复杂地面上“如履平地”，但未详细说明采用 VLA、世界模型或具体 RL 算法。[39]

---

## 第三章 产品进度与商业化落地

本章按场景梳理代表性产品的落地阶段与案例。鉴于部分公司未公开部署规模，本报告仅基于公开证据描绘 Demo/试点/部署阶段。

### 3.1 人形机器人：从演示到试点部署

#### 3.1.1 Agility Digit：仓储与工厂试点

- Agility 官方新闻指出，Digit 已在 GXO 和 Schaeffler 等客户现场试点部署，用于箱件搬运与托盘化任务。[13]
- 这些试点在仓库与生产线中验证了 Digit 在物料搬运与自动化升级中的适用性，并被描述为从研究阶段迈向商业部署的重要步骤。[13]
- NVIDIA 案例进一步说明 Digit 在仿真中接受大规模训练后，部署于实体 Digit 执行复杂动态任务，表明该系统已具备一定程度的实地稳定性。[33]

综合来看：

- Digit 在 2020s 中期已达到**客户现场试点部署**阶段，在少数客户场景中进行箱件搬运与托盘化任务验证。
- Arc 平台支持任务编排与车队管理，为进一步规模化部署提供基础。[11]

#### 3.1.2 Sanctuary Phoenix：零售与仓储试点

- Sanctuary 官方称 Phoenix 为“世界上首批由 Carbon 控制的通用人形机器人之一”，并列举其在零售与仓储场景中执行的任务，包括点货、搬运和操作终端设备。[14]
- Phoenix 第七代在关节活动范围、系统可用性与视觉和触觉感知方面均有提升，旨在支持更复杂操作任务。[40]

现有证据表明：

- Phoenix 已在真实商业环境中执行多类任务，处于**试点到早期商业部署**阶段；
- 其通用性目标是“在为人类设计的环境中工作”，强调跨任务和跨场景能力。[14][40]

#### 3.1.3 Figure 03：通用人形平台的早期部署

- Figure 新闻稿指出 Figure 03 面向物流、制造和家庭等场景，并强调可在仓库和生产线 24/7 运行。[8]
- Figure 03 与 Helix 深度集成，旨在支持“未显式编程的任务”，即通过 VLA 模型对自然语言或任务描述进行解释后，生成操作序列。[30]

图谱中未包含具体客户案例或部署规模，因此本报告仅将 Figure 03 定位于**已公开技术方案与 Demo 展示、面向工业与家庭的大规模部署目标阶段**。

#### 3.1.4 Boston Dynamics Atlas：面向真实工业工作的演示与合作

- Boston Dynamics 表明最新一代电驱 Atlas 旨在面向真实工业工作，提高力量密度和灵活性，通过动态平衡与全身协调控制执行高强度物料搬运和自动化生产线任务。[69]
- 官方博客提到与工业伙伴合作，将 Atlas 用于物料搬运与自动化生产线升级，但未给出具体客户与部署规模。

因此，Atlas 当前可视为处于**与工业伙伴合作的试点与演示阶段**，其商业化路径偏向高强度工业任务。

### 3.2 仓储物流机器人与 AMR

虽然本报告重心在人形与具身智能，但部分证据也强调仓储物流机器人/AMR 的作用：

- Agility Digit 作为仓储机器人在人类空间执行搬运任务，是连接自动化孤岛的重要补充。[11][13]
- Boston Dynamics Stretch（与 Spot、Atlas 一起）形成“检测—搬运—复杂操作”的组合，从而为仓储与物流提供完整自动化方案。[69]

由于图谱未收录 Geek+、Locus、京东物流等公司详细证据，本报告不对这些公司做扩展叙述。

### 3.3 家用服务机器人与协作机器人

#### 3.3.1 1X NEO：家用机器人

- NEO 被定位为家用机器人，使用 Redwood AI 通用模型，具备基础自主能力，并通过持续学习提升家务辅助、陪伴看护和家庭安全等任务的能力。[37]
- 目前材料主要为产品介绍与愿景，未包含大规模家用部署的量化数据，可视为**面向家庭用户的早期产品化与试点阶段**。

#### 3.3.2 UBTECH 与教育/服务机器人

- UBTECH 提供多类教育与服务机器人及 Walker 系列人形平台，并在 AI 教育、安防巡检和智能制造等行业开展解决方案。[10]
- 图谱中未提供具体部署数量与客户案例，故本报告将其定位为**在多场景提供解决方案并进行行业部署**，但不对规模做数值描述。

---

## 第四章 融资格局与资本热点

本章仅根据已收录证据描述资本格局与典型公司融资情况，不额外引入外部数据。

### 4.1 机器人基础模型与“Physical AI”赛道

一篇关于“Physical AI 2026”的产业分析指出，构建通用机器人基础模型和相关基础设施成为新的资本热点。[16]

- 文中提到，Physical Intelligence 等公司在 2026 年前后已经筹集约 4 亿美元规模资金，用于开发通用机器人基础模型，并构建云训练与大规模场景数据采集基础设施。[16]
- 该分析把这种“基础模型 + 具身智能”的路径称为“Physical AI”，认为其是未来多家公司布局的方向之一。[16]

因此：

- 2022-2026 年间，围绕机器人基础模型的融资总体处于**数亿美元量级**；
- 资本投入重点包括：通用机器人基础模型的训练、云基础设施及大规模数据采集。

### 4.2 人形/具身机器人公司融资（Figure、Agility、1X、Sanctuary 等）

图谱中的融资数据相对有限，主要通过行业分析与公司介绍进行间接呈现：

- Figure、Agility、1X、Sanctuary 及其他人形公司被多篇行业文章列为“构建通用人形机器人和机器人基础模型的代表性公司”，但具体轮次与估值在图谱中并未统一呈现。[19][70][71]
- 对 Physical Intelligence 这类公司，存在不同来源对融资规模的口径差异（例如“数亿美元”、“约 4 亿美元”等描述），本报告统一用“约数亿美元”表述，以涵盖不同口径。[16]

在缺乏统一统计的前提下，本报告不对具体轮次、估值排名或投资机构列表做定量总结，而仅从方向上归纳：

- 高度关注机器人基础模型与通用人形平台的公司（如 Figure、Agility、Sanctuary、1X、Physical Intelligence）是资本集中度较高的集合。
- 投资方包括通用风投、产业资本及可能的大厂战略投资，但图谱未给出详细结构。

### 4.3 资本热度演变

- VLA 与机器人基础模型被行业文章称为“下一代机器人范式”，预计将支撑未来通用机器人，表明资本市场对该路线的长期看好。[19]
- 风险投资机构从世界模型角度提出，具有强世界模型能力的机器人可显著减少数据需求并提高规划能力，从投资角度看更具可扩展性和复用价值。[51]

总体而言：

- 2022-2023 年：RL、模仿学习与特定任务机器人仍占主流；
- 2024-2026 年：VLA、基础模型、世界模型及其混合架构成为资本关注焦点，特别是在通用人形和家用机器人方向。

---

## 第五章 团队与人才画像

本章基于图谱中可见的团队与人才信息进行归纳，明确区分事实陈述与趋势性判断。

### 5.1 Figure：多方经验融合的 AI-first 团队

- Figure 官网指出其团队在 AI 与 humanoid robotics 方面具有丰富经验，成员来自 Boston Dynamics、Tesla、Apple 等公司。[7]
- 这表明 Figure 核心团队由具备大规模 AI 与机器人经验的复合背景人才组成。

从组织结构上看：

- 招聘信息显示 Figure 在技术栈中设置感知、全身控制、规划与操作等分工，说明其组织结构与技术模块紧密对应。[7]

此类团队特点包括：

- 兼具大模型经验与机器人控制经验；
- 强调端到端学习与仿真训练能力。

### 5.2 Tesla Optimus：大模型与 RL/IL 专长的复合团队

- Tesla 的 Optimus 项目招聘“Vision & Foundation Models”与“Reinforcement Learning Engineer, Policy”等岗位，表明其团队既包含大规模基础模型专家，也包含强化学习和模仿学习工程师。[31][32]
- 结合 Tesla 在自动驾驶领域的经验，可以判断其团队结构偏向“感知与基础模型 + 端到端策略学习”的组合。

### 5.3 Agility、Sanctuary、1X：基础模型与控制的跨学科团队

- Agility Digit 的控制架构依托 NVIDIA 平台的 Whole-Body Control Foundation Model，需要在仿真、GPU 加速训练与全身控制方面具备深厚经验；NVIDIA 案例表明双方合作紧密。[33]
- Sanctuary 的 Carbon 架构将深度学习、强化学习和符号认知结合，要求团队在现代机器学习与经典 AI（符号规划、知识表示）方面具有交叉能力。[35]
- 1X 的 Generalist AI 和 Redwood 模型表明其团队需要既有大模型研发经验，又能解决家用机器人安全和人机交互问题。[36][37][70]

### 5.4 中国公司：本土产业经验与学术合作

- UBTECH 的产品线覆盖教育、服务、安防与 Walker 人形机器人，说明其团队既服务消费与教育市场，也面向安防与制造场景。[10]
- 宇树及相关论文所展示的 H1 系列 RL 起身策略表明，其团队与学术机构合作，在强化学习和人形动态控制方面展开研究。[38][39]

综合来看：

- **北美/硅谷创业公司（Figure、1X、Physical Intelligence 等）**：团队往往聚合来自顶级科技公司和研究机构的多模态大模型与机器人控制人才，倾向“AI-first + 基础模型”架构。[7][16][36]
- **中国本土企业（UBTECH、宇树等）**：更强调在本土行业场景中的部署与工程能力，结合传统控制与新兴 RL/IL 技术，并通过与高校和研究机构合作推进算法创新。[10][38][39]

这些趋势判断基于有限样本与公开招聘/产品信息；对非公开的团队结构与人数，本报告不作推断。

---

## 第六章 投资视角下的路线对比与风险提示

本章在前述证据基础上，从投资角度对不同技术路线与公司类型进行比较，并给出决策建议与风险提示。

### 6.1 不同技术路线的比较

#### 6.1.1 数据需求与训练成本

- **VLA / 机器人基础模型**：依赖组合的 web 规模多模态数据与机器人轨迹，训练成本高，但可在多任务和新任务上提供较强的泛化能力。[19][20][57][59]
- **端到端 RL**：在高性能控制任务中表现优秀，但在实际机器人上存在样本效率和安全性问题，需大量交互或通过离线 RL 与仿真减少真实试错。[21][22][46][47]
- **模仿学习**：在接触丰富任务中，通过高质量示教可在较低样本成本下达到较好效果，但对示教质量敏感，需要处理示教者水平差异。[23][24][52]
- **世界模型**：通过在模拟中进行大量训练，减少真实数据需求；物理约束世界模型进一步提高模拟可靠性。[26][28][51]

从投资角度，**基础模型 + 世界模型**路线在长期上更具数据复用优势，但早期投入巨大；**RL/IL + 仿真**路线在特定任务上更容易实现短期里程碑。

#### 6.1.2 泛化能力与应用范围

- VLA/基础模型通过联合多任务、多场景训练，已经在实验中显示优于窄域基线的泛化能力。[59][60]
- π0.7 等模型展示了“组合泛化”，可在未进行任务特定训练情况下执行组合任务。[63]
- 世界模型配合模型式 RL，有望通过更强的环境理解支持长时规划和跨任务迁移。[27][28][51]

因此，在面向工业与家庭多任务场景时，**VLA + 世界模型 + 分层控制**更具潜在泛化优势。

#### 6.1.3 落地场景与收入路径

- **工业与仓储**：Agility Digit 与 Boston Dynamics Atlas 等围绕物料搬运和自动化升级，已在试点与合作中验证价值。[11][13][69]
- **零售与仓储服务**：Sanctuary Phoenix 在零售与仓储执行点货与终端操作任务，展示通用人形在现有商业环境中的应用潜力。[14]
- **家用与服务**：1X NEO 与 UBTECH 教育/服务机器人面向家庭和教育场景，但大规模家用部署尚在早期阶段。[10][37]

在短期内，**工业与仓储场景**由于 ROI 可见、任务结构相对明确，是最先形成稳定收入的方向；家用与真正通用人形机器人仍处于产品化与试点阶段。

#### 6.1.4 资本密度与竞争格局

- VLA、基础模型与世界模型路线需要大量算力与数据投入，资本密度高；Physical Intelligence 等公司已筹集约数亿美元资金。[16]
- 工业与仓储机器人（Digit、Atlas 等）通过与大厂平台（如 NVIDIA Isaac）合作，形成“技术 + 基础设施 + 客户场景”三位一体，资本与技术门槛均较高。[33][65]
- 家用与教育机器人则在硬件成本与软件能力之间权衡，竞争更加多样化（包括传统服务机器人厂商与新兴基础模型公司）。

### 6.2 公司类型对比

结合前文证据：

- **AI-first 基础模型公司（Figure、Physical Intelligence、π0 等）**：  
  - 优势：在基础模型与世界模型方面有先发优势，具备较强的技术叙事；[7][16][20][63]
  - 风险：短期落地场景有限，商业模式需依赖与硬件公司或行业伙伴的合作。
- **工业/仓储导向人形公司（Agility、Boston Dynamics、Sanctuary）**：  
  - 优势：在具体场景（仓储、制造、零售）已有试点或合作，具备较强落地能力；[11][13][69][14]
  - 风险：场景定制化程度高，需要兼顾可扩展性与客户共性需求。
- **家用/服务型公司（1X、UBTECH 等）**：  
  - 优势：面对庞大潜在用户群，产品一旦成熟可形成规模市场；[10][36][37]
  - 风险：家庭环境多样性与安全性要求高，对基础模型和世界模型提出更高要求，且缺乏短期高价值场景。

### 6.3 对投资人的启示与建议

基于图谱证据，面向专业投资人可提出以下高层建议（为分析性的判断，而非事实陈述）：

1. **优先关注“基础模型 + 场景闭环”的公司**  
   具备 VLA/基础模型能力且在工业或仓储等场景中已有试点部署的公司（如采用 Whole-Body Control Foundation Model 的 Digit，或 Helix+Figure 03 方案）在技术与落地之间更易形成闭环。[8][13][33]
2. **评估世界模型投入与仿真基础设施**  
   具备物理约束世界模型、视频世界模型与大规模仿真能力的团队，在数据效率与长时规划方面具有潜在优势；投资应关注其仿真平台与真实数据采集能力。[28][29][51][65]
3. **审视团队跨学科能力与组织结构**  
   成功的具身智能团队往往同时具备基础模型、大规模训练、机器人控制与符号认知等多方面能力。Figure、Sanctuary、1X 等公司的招聘与架构显示，跨学科团队是实现混合架构的关键。[7][35][36]
4. **在资本结构与估值上保持口径敏感**  
   Physical Intelligence 等公司的融资规模在不同来源中存在表述差异（如“数亿美元”、“约 4 亿美元”），反映出统计口径与时间点差异；投资分析应关注数据来源并接受区间估计，而非依赖单一数字。[16]
5. **平衡短期收益与长期潜力**  
   工业与仓储场景可在 3-5 年内提供更明确的现金流，而家用与真正通用人形机器人可能需要更长的技术与市场培育周期。投资组合可采用“工业/仓储稳健 + 基础模型与世界模型远期期权”的结构。

### 6.4 主要风险与研究局限

本报告在基于图谱证据的基础上，存在以下局限与风险：

- **数据不完整**：图谱未覆盖所有具身智能公司和项目，尤其是部分中国公司与传统仓储机器人企业，其商业化数据未被纳入。
- **技术栈透明度有限**：许多公司未公开内部控制架构细节，本报告仅基于公开招聘、技术博客与案例文字进行分析，不对未披露部分做推断。
- **估值与融资数据口径差异**：不同来源对融资金额和估值给出的数字可能存在差异，本报告仅在有明确证据时使用“约数亿美元”“数亿美元”等区间描述，而不采用精确数字。[16]
- **时间窗口与快速演化**：具身智能技术在 2025-2026 年仍快速演化，本报告基于截至 2026 年上半年图谱数据进行分析，后续进展可能改变部分结论。

---

## 参考文献

[1] ‘The Great Replacement’: 5 robots replacing human workforce in 2026 https://www.wionews.com/photos/the-great-replacement-5-robots-replacing-human-workforce-in-2026-1780553633059

[2] Investors bet humanoid robots will transform industry and homes over the next decade https://www.cnbc.com/2026/06/03/humanoid-robots-trillion-dollar-ai-market.html

[3] Silicon Valley's new slogan: Let's get physical https://www.businessinsider.com/silicon-valleys-new-slogan-lets-get-physical-2026-6

[4] 全球6大仓储机器人独角兽的2025：谁在领跑？ https://www.eet-china.com/mp/a469093.html

[5] 穿越热潮：2025具身智能机器人场景应用白皮书重磅发布 https://www.ageclub.net/article-detail/8697

[6] 普渡机器人创始人张涛：中国服务机器人走向世界-民营企业家典型事迹 https://fgw.sz.gov.cn/ztzl/qtztzl/szscjmyjjfzzhfwpt/mqfc/myqyjdxsj/content/post_12623955.html

[7] Advancing the Integration of Robots and AI to Drive Technological Innovation https://global.toyota/en/mobility/frontier-research/42394425.html

[8] A Survey on Vision-Language-Action Models for Embodied AI https://arxiv.org/html/2405.14093v6

[9] Vision-Language-Action Models for Embodied Intelligence https://pub.scientificirg.com/index.php/CDIS/article/view/75

[10] Modern Vision-Language-Action Models (CS7643 Lecture L24 Embodied Intelligence) https://faculty.cc.gatech.edu/~zk15/teaching/AY2026_cs7643_spring/assets/L24_EmbodiedIntelligence.pdf

[11] Multimodal Fusion with Vision-Language-Action Models for Robotic Manipulation https://muhayyuddin.github.io/VLAs/

[12] 10 Open Challenges Steering the Future of Vision-Language-Action Models https://jiajunwu.com/papers/vlachallenges_aaaismt.pdf

[13] Vision-language-action models are the next leap in autonomous robotics https://www.therobotreport.com/vision-language-action-models-are-the-next-leap-in-autonomous-robotics/

[14] Google unveils RT-2 AI language model for robots https://siliconangle.com/2023/07/28/google-unveils-rt-2-ai-language-model-telling-robots/

[15] Vision-language-action models enable robots to complete complex tasks https://www.nature.com/articles/s42256-025-01005-x

[16] DeMaVLA: A Vision-Language-Action Foundation Model for Household Robots https://arxiv.org/html/2605.31286v1

[17] RoboMamba: Efficient Vision-Language-Action Model for Robotic Manipulation https://neurips.cc/virtual/2024/poster/95690

[18] VLA Models in Robotics 2026: RT-2 vs OpenVLA vs π0 vs MolmoAct 2 https://robocloud-dashboard.vercel.app/learn/blog/vla-models-robotics-2025

[19] GR00T N1: An Open Foundation Model for Generalist Humanoid Robots https://www.researchgate.net/publication/390019361_GR00T_N1_An_Open_Foundation_Model_for_Generalist_Humanoid_Robots

[20] π0 / π0.7: a Steerable Generalist Robotic Foundation Model with Emergent Compositional Generalization https://arxiv.org/html/2604.15483v1

[21] Building General-Purpose Robot Autonomy: A Progressive Roadmap https://rpl.cs.utexas.edu/research/

[22] Physical AI in 2026: What It Is, Key Models, and How to Build It https://www.roboticscenter.ai/blog/physical-ai-2026-guide

[23] NVIDIA Isaac GR00T N1 – open humanoid robot foundation model announcement https://www.facebook.com/NVIDIARobotics/posts/at-rss2025-nvidiaresearch-is-advancing-agile-humanoidrobot-control-sim-to-real-t/1213933837443982/

[24] Deep Reinforcement Learning for Robotics: A Survey of Real-World Applications https://www.annualreviews.org/content/journals/10.1146/annurev-control-030323-022510

[25] Taxonomy and Trends in Reinforcement Learning for Robotics and Autonomous Systems https://arxiv.org/html/2510.21758v3

[26] Comparing Reinforcement Learning with Behavioural Cloning for Flight Control https://esa.int/gsp/ACT/projects/rl_vs_imitation_learning/

[27] Offline Reinforcement Learning on Real Robots with Realistic Data https://neurips.cc/virtual/2022/60686

[28] Robotic Manipulation Datasets for Offline Compositional Reinforcement Learning https://www.seas.upenn.edu/~eeaton/papers/Hussing2024RoboticManipulation.pdf

[29] Uni-O4: Unifying Online and Offline Deep Reinforcement Learning https://openreview.net/forum?id=tbFBh3LMKi

[30] A Survey of Reinforcement Learning from Human Feedback https://arxiv.org/pdf/2312.14925

[31] Reinforcement Learning from Human Feedback – RLHF Book https://rlhfbook.com/book.pdf

[32] A Survey on Imitation Learning for Contact-Rich Tasks in Robotics https://arxiv.org/html/2506.13498v1

[33] Interactive Imitation Learning for Dexterous Robotic Manipulation https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1682437/full

[34] Compositional World Models Empowering Robot Imitation Learning with Imagination (Dream to Manipulate) https://openreview.net/forum?id=3RSLW9YSgk

[35] Imitation Learning by Estimating Expertise of Demonstrators (news item) https://iliad.stanford.edu/news/

[36] Understanding World or Predicting Future? A Comprehensive Survey of World Models https://arxiv.org/html/2411.14499v4

[37] A Survey of Embodied World Models https://www.preprints.org/manuscript/202604.0928

[38] RoboScape – Physics-informed Embodied World Model https://neurips.cc/virtual/2025/poster/115313

[39] Can world models unlock general purpose robotics? https://www.bvp.com/atlas/can-world-models-unlock-general-purpose-robotics

[40] Towards Video World Models https://www.xunhuang.me/blogs/world_model.html

[41] A Comprehensive Survey on Embodied AI https://arxiv.org/html/2407.06886v8

[42] Embodied AI: A Survey on the Evolution from Perceptive to Interactive Agents https://onlinelibrary.wiley.com/doi/full/10.1002/smb2.70003

[43] Survey of Embodied Artificial Intelligence Data: From Simulators to Research Tasks https://airs.cuhk.edu.cn/sites/default/files/2025-06/Survey_Arxiv.pdf

[44] DAM-VLA: A Dynamic Action Model-Based Vision-Language-Action Framework for Robot Manipulation https://research.samsung.com/blog/DAM-VLA-A-Dynamic-Action-Model-Based-Vision-Language-Action-Framework-for-Robot-Manipulation

[45] Knowledge Insulating Vision-Language-Action Models https://neurips.cc/virtual/2025/poster/117079

[46] Awesome-Multimodal-Embodied-AI (includes VLaser, Embodied-R1 etc.) https://github.com/Hoar012/Awesome-Multimodal-Embodied-AI

[47] Figure Exceeds $1B in Series C Funding at $39B Post-Money ... https://www.figure.ai/news/series-c

[48] Figure AI valuation, funding & news | Sacra https://sacra.com/c/figure-ai/

[49] 100+ Figure Ai Statistics: 2026 Verified Report - WifiTalents https://wifitalents.com/figure-ai-statistics/

[50] Figure raises $1B, valued at $39B, to ship humanoid robots - LinkedIn https://www.linkedin.com/posts/figure-ai_announcing-figure-has-exceeded-1b-in-funding-activity-7373703158998446082-f5mJ

[51] 1X Secures $100M in Series B Funding https://www.1x.tech/discover/1x-secures-100m-in-series-b-funding

[52] 1X Business Breakdown & Founding Story - Contrary Research https://research.contrary.com/company/1x

[53] 1X Technologies - Wikipedia https://en.wikipedia.org/wiki/1X_Technologies

[54] Sanctuary AI Announces Strategic Financing From BDC Capital and ... https://www.sanctuary.ai/blog/sanctuary-ai-announces-strategic-financing-from-bdc-capital-and-inbc

[55] Accenture Invests in Sanctuary AI to Bring AI-Powered, Humanoid ... https://newsroom.accenture.com/news/2024/accenture-invests-in-sanctuary-ai-to-bring-ai-powered-humanoid-robotics-to-work-alongside-humans

[56] Agility Robotics valuation, funding & news | Sacra https://sacra.com/c/agility-robotics/

[57] Agility Robotics Raises $400M on $2.15B valuation - ONAMI https://onami.us/news/agility-robotics-raises-400m-on-2-15b-valuation

[58] 90后机器人创业者，再次获得近10亿元人民币融资 - Unitree Robotics https://www.unitree.com/cn/mobile/news/11

[59] 宇树科技股份有限公司首次公开发行股票并在科创板上市招股说明书 https://static.sse.com.cn/stock/disclosure/announcement/c/202603/002178_20260320_QY8F.pdf

[60] 深度拆解宇树科技招股书：一年营收17亿，宇树机器人都卖给了谁？ https://www.eeo.com.cn/2026/0320/813654.shtml

[61] 净利3亿，估值420亿！宇树科技冲刺IPO，王兴兴持股23.82% https://www.stcn.com/article/detail/3735182.html

[62] UBTECH ROBOTICS CORP LTD 深圳市優必選科技股份有限公司 https://stockn.xueqiu.com/09880/20260331095340.pdf

[63] 优必选（09880.HK） 国内人形机器人领军企业 https://pdf.dfcfw.com/pdf/H3_AP202501271642599868_1.pdf?1738005880000.pdf

[64] 机器人公司丰疆智能（FJ Dynamics）宣布完成4.46亿B轮融资 - 亿欧 https://www.iyiou.com/news/202111301025160

[65] 前大疆首席科学家吴迪创办的丰疆智能冲刺港股：上半年营收3.6亿亏 ... https://m.36kr.com/p/3486169733536904

[66] 智元机器人| 项目信息 - 36氪 https://pitchhub.36kr.com/project/2228936046528520

[67] Introducing Figure 03 - Figure AI https://www.figure.ai/news/introducing-figure-03

[68] AI & Robotics | Tesla https://www.tesla.com/AI

[69] AI Engineer, Vision & Foundation Models, Optimus - Tesla https://www.tesla.com/careers/search/job/ai-engineer-vision-foundation-models-optimus-233307

[70] Figure AI https://www.figure.ai/

[71] Atlas Humanoid Robot - Boston Dynamics https://bostondynamics.com/products/atlas/
