## 引言

近三年（约 2022–2026 年），以人形机器人为代表的具身智能（Embodied Intelligence / Embodied AI）进入产业加速期。一方面，学术界围绕“具身基础模型”“世界模型”“Vision‑Language‑Action（VLA）”等方向形成了相对清晰的技术谱系，提出具身智能系统由感知、认知、控制和身体四个层次构成，并在导航、操纵、交互等任务上形成系统分类框架[1][2]。另一方面，Tesla、Figure、1X、Sanctuary、Agility、Apptronik、Boston Dynamics、宇树、智元、优必选、傅利叶、小米等企业，以及 OpenAI、Google DeepMind、NVIDIA、百度、阿里、华为等大模型与平台方，正在围绕“通用机器人”“具身大模型”展开产品化与商业化竞赛[3]。

本报告基于 2022–2026 年公开文献、公司官网、行业报告和新闻资料，对全球具身智能的主要技术路线进行系统梳理，并选取北美、中国、欧洲/日本/以色列等代表性公司，从以下五个维度进行对比分析：

1. 技术路径：模型架构、算法特点、软硬件一体化思路；
2. 产品形态与研发/落地进度；
3. 商业化进度：盈利模式、客户类型、订单与收入（如有公开）；
4. 融资情况：融资轮次、代表投资方、估值（如有公开）；
5. 团队情况：创始人/技术负责人背景、团队规模与构成。

报告面向具备一定 AI/机器人背景的行业研究者，重点强调可验证事实与公开路径，对推测性信息会明确标注来源性质和不确定性。

---

## 一、具身智能技术路线综述

### 1.1 概念与分层结构

最新的具身智能综述指出，具身智能系统可从四个层次进行结构化划分：感知层、认知层、控制层和身体层[1]。感知层负责多模态传感（视觉、语音、触觉等），认知层负责任务理解、规划与推理，控制层将高层计划转化为轨迹和关节控制，身体层则是机器人本体和执行机构[1][4]。具身智能区别于传统机器人控制的关键在于：

- 更强调通过数据驱动与大模型学习跨任务、跨场景的通用能力，而非针对单一任务手工设计管线；
- 更强调感知—认知—控制—身体的闭环协同，而非单点算法优化。

具身 AI 相关综述进一步从任务、系统架构和训练范式三个维度建立了主流 taxonomy[2]：

- 任务维度：导航（Navigation）、操纵/操作（Manipulation）、交互（Interaction）；
- 架构维度：端到端策略网络（end‑to‑end policy）、模块化流水线（modular pipeline）、基于世界模型系统（world‑model‑based systems）、基于 VLM/VLA 的系统（VLM/VLA‑based systems）[2][5]；
- 训练范式维度：模仿学习/行为克隆（IL/BC）、强化学习（RL）、自监督表示学习，以及由大语言/多模态模型引导的训练方式（LLM‑guided training）[2]。

这一框架为理解产业界多种技术路线的组合提供了统一参考。

### 1.2 核心技术路线

结合综述、GitHub 资源库以及各公司技术文档，可以将近三年的具身智能主流技术路线概括为以下几大类。

#### 1.2.1 端到端多模态策略网络：RT 系列与通用策略 π₀

- RT‑1：Google Robotics 提出的 Robotics Transformer，将视觉帧、任务语言指令和机器人状态作为输入，通过单一 Transformer 策略网络直接输出离散化动作 token，实现基于行为克隆的大规模多任务控制[6][7][8]。
- RT‑2：在 RT‑1 的基础上提出 Vision‑Language‑Action（VLA）模型，先在 web 规模图文数据上进行视觉‑语言预训练，再在机器人示教数据上扩展为 VLA，使机器人能够利用 web 语义知识执行训练数据中未见过的抽象任务，被视为“机器人基础模型”的范式代表[9][10][11][12]。
- π₀：Physical Intelligence 团队提出的基于 flow 的 VLA 通用策略，将视觉、语言和状态编码到统一表示，使用条件 flow 模型输出动作分布，在多平台、多任务场景中通过离线模仿学习训练[13][14][15]。后续实证研究指出，当前通用策略大多是无显式记忆的单步策略，在长时序任务和分布外场景下存在明显局限[16][17]。

这一路线的特点是：

- 优点：工程结构简洁，训练/推理闭环清晰，便于在单平台快速迭代；适合利用大规模示教数据直接学习多任务策略；
- 局限：长时序规划能力不足、安全性与可解释性有限，难以直接在对安全和稳定性要求极高的工业场景中单独使用。

#### 1.2.2 具身基础模型与 VLM/VLA：从 web 知识到机器人控制

具身 AI 综述提出“具身基础模型（embodied foundation models）”概念，将视觉、语言和动作统一到大模型中，在多任务、多机器人平台上实现通用控制[2][5][18]。RT‑2 即为典型 VLA 实例[9][10]。相关 GitHub 资源列表系统整理了 VLM/VLA 驱动的机器人工作，包括视觉‑语言导航、VLM+控制器组合、端到端 VLA 模型等[19][20]。

VLM/VLA 具身基础模型的核心思路是：

- 利用 web‑scale 图文数据获得广泛的语义知识；
- 在此基础上使用相对少量的机器人数据进行动作头微调，把语义映射到物理动作[9][10]；
- 支持通过自然语言提示（prompting）配置任务，实现“语义到动作”的迁移。

这一方向已被 Google DeepMind、OpenAI 等视为构建具身智能通用层的重要路径，但更多处于研究和早期产品化阶段。

#### 1.2.3 世界模型（World Models）+ 规划

世界模型综述将面向具身智能的世界模型定义为“能够预测环境未来状态或观测的模型”，并将其分为：基于模型的 RL（model‑based RL）、潜在空间动力学模型（latent dynamics models）、生成式视频/世界模型（generative video / world models）以及可微分模拟器（differentiable simulators）[21][22]。世界模型在导航、操纵和多步规划中可通过模型预测控制（MPC）或“想象”未来轨迹来提高样本效率与安全性，但现实部署时面临动力学建模误差与工程复杂性[21][23]。

最新的“World Models for Vision‑Language‑Action Agents”工作进一步探讨将世界模型扩展到 VLA 代理，在多模态嵌入空间中学习环境动态，用于长时序任务中的规划与评估[3][24]。

对于产业界来说，世界模型的直接应用仍较少，但在百度百舸、华为 CloudRobo 等平台中已被作为面向具身智能训练和仿真的重要能力模块。

#### 1.2.4 LLM 驱动的模块化机器人系统

EmbodiedGPT 将大语言模型引入具身任务，通过“具身 chain‑of‑thought”训练，上层 LLM/VLM 负责理解语言指令和视觉场景、生成语言化中间步骤，下层控制器根据这些子任务执行动作[25][26]。该路线的特点是：

- 高层使用 LLM 进行任务分解、长时推理和工具调用；
- 低层保持传统控制或专用策略网络，保障稳定性和安全性；
- 有利于解释性和人机协作，也利于快速对接多类机器人。

产业界的许多实践（如 Gemini Robotics‑ER、Figure Helix、Sanctuary Carbon AI、部分国内“具身智脑”方案）在工程架构上与此类似，即“高层大模型 + 低层控制栈”的分层结构[27][28][29][30]。

#### 1.2.5 云边协同：云端大模型 + 边缘控制

Figure AI 的 Helix 架构是“云大模型 + 边缘人形机器人”的典型案例：Helix 作为云端多模态 AI“大脑”负责感知、语言理解和任务规划，人形机器人本体在边缘执行实时控制与安全闭环[27][31][28]。报道将这一模式概括为“cloud AI brain + edge humanoid body”，既充分利用云端算力，又兼顾现场实时性[31]。

中国的“慧思开物”平台、百度百舸、华为 CloudRobo、阿里通义具身团队等，也大多采用“云端具身大脑 + 多种机器人本体”的架构。

#### 1.2.6 传统分层控制 + 局部智能：工业级落地主流

在工业机器人与早期人形部署中，传统分层控制仍是主流工程选择：

- Agility 的 Digit 采用明确分层的软件栈：感知（建图、障碍物检测）+ 局部/全局路径规划 + 步态与避障控制，并通过 Arc 工作流平台进行上层任务编排，更接近“工业自动化 + 局部智能”路线，而非端到端大模型[32][33][34]。
- UBTECH Walker S2 在制造业场景采用 dual‑loop AI system，即任务规划层 + 运动控制层的双环路分层控制[35][36]。
- 傅利叶在工业方案中强调全身动力学动量优化和轨迹规划算法，结合双臂冗余自由度实现协同操作，再配合 RL 在仿真环境中训练运动策略后迁移到实体机器人[37][38][39]。

这些方案体现出：在对安全、稳定性要求极高的工厂、仓储等场景，大模型更常作为上层决策与感知模块，而运动控制仍大量依赖传统控制与优化。

### 1.3 数据与基础设施：跨机器人数据集与训练平台

具身智能的核心瓶颈是数据。Google 等提出 Open X‑Embodiment 数据集与模型，聚合多种机器人形态与任务的数据，旨在为跨平台具身训练提供统一资源[40][41]。GitHub 上的 Embodied World Models 与 Embodied AI 资源列表，则系统梳理了各类数据集、仿真平台与现实平台[19][20][42]。

在基础设施层面：

- 百度百舸平台为具身智能提供从仿真、世界模型到策略优化的全栈加速方案，为创新中心与企业提供算力与训练平台；
- 华为 CloudRobo 提出“具身规划大模型 + 具身执行大模型 + 具身世界大模型 + 工具链”的三大模型 + 工具链平台，并依托 Ascend/Atlas 系列提供端‑边‑云算力；
- NVIDIA 通过 Isaac 仿真平台、人形机器人基础模型和 Project GR00T 等，联合 Figure、Agility、Apptronik、Boston Dynamics 等构建人形机器人生态，被视为具身智能底层平台提供方。

---

## 二、全球代表性公司与类型划分

结合行业报告和公司资料，可以将具身智能代表性公司大致分为三类：

1. **人形/通用机器人整机厂商**  
   - 北美：Tesla（Optimus）、Figure AI、1X、Sanctuary AI、Agility Robotics、Apptronik、Boston Dynamics 等；
   - 中国：智元、宇树、优必选、傅利叶、乐聚、众擎、小米等；
   - 欧洲/日本/其他：PAL Robotics、Engineered Arts、Toyota Research Institute、Honda、SoftBank Robotics、Mentee Robotics 等[43][44][45][46][47][48]。

2. **具身大模型与“机器人中枢”平台方**  
   - OpenAI、Google DeepMind（Gemini Robotics / RT 系列）、NVIDIA（Isaac/Project GR00T）、百度（文心 + 百舸）、华为（CloudRobo + 盘古 + Ascend）、阿里（通义具身团队 + RynnRCP）、Unifolm（RoboBrain 2.0）等[9][10][27]。

3. **场景型应用公司与长尾玩家**  
   - Covariant（仓储/物流机械臂 + 机器人基础模型 Covariant Brain）[49]；
   - 教育与服务机器人（UBTECH、乐聚、SoftBank Robotics 等）[50][51][44][52]。

后续章节将围绕重点玩家展开逐一分析。

---

## 三、北美代表性公司分析

### 3.1 Tesla：端到端神经网络 + 工厂内部试用

**技术路径**

- Tesla 在 FSD 和 Optimus 上采用统一的端到端神经网络架构和数据引擎：多摄像头等传感器输入经过数十个神经网络协同工作，输出大规模张量表示，实现感知与决策一体化[42][53]。
- 官方 AI 页面明确 Optimus 共享 FSD 的数据引擎和仿真体系，表明其训练路径依托统一自动标注和仿真基础设施[42][53]。
- 二手投资者分析认为 Optimus 早期通过人类遥操作采集示教轨迹（tele‑operation），并利用类似 FSD 的大规模数据闭环进行持续训练，但这属于推测性观点，并非官方技术文档[54][55]。

整体上，Tesla 路线可视为“端到端具身神经网络 + 统一数据引擎 + 仿真”的一体化体系。

**产品与落地进度**

- 行业博客称 2023 年 12 月发布 Optimus Gen 2，作为接近量产形态的人形机器人，相比早期原型在外观、移动、感知和操作上有改进。
- 据二手报道，Optimus Gen 2 自 2024 年中起在弗里蒙特和奥斯汀工厂内部进行“dogfooding”试用，用于搬运和物料转运等任务，尚未对外销售。

这些信息主要来自行业博客，属于非官方、未经证实的推测性资料，使用时需注意其不确定性。

**商业化与团队/融资**

- Optimus 为 Tesla 内部项目，无单独对外融资与估值披露。其商业化策略预计以“内部大规模部署 + 对外销售”两步走，但具体节奏与定价尚未公开。
- 团队层面，Optimus 依托 Tesla Autopilot/FSD 的 AI 和机器人团队，强调跨汽车和人形机器人的技术复用[42][53]。

### 3.2 Figure AI：Helix 具身大脑 + 云边协同

**技术路径**

- Figure 采用 Figure 02/03 人形机器人平台，结合名为 Helix 的云端多模态 AI 模型，Helix 作为高层“大脑”，负责多模态感知、语言理解和任务规划，机器人本体负责边缘实时控制[27][31][28]。
- Project Go‑Big 项目致力于构建“全球最大、最具多样性的人形预训练数据集”，通过合作伙伴在真实场景采集多任务、多环境数据，为通用人形模型的互联网规模预训练和持续增量学习提供数据基础[56][29]。

整体路径可描述为：“云端 Helix 大模型 + 大规模真实多任务预训练数据 + 边缘人形机器人本体”的云边协同具身智能。

**产品与落地进度**

- Figure 02：全尺寸双足通用人形，已在 BMW Spartanburg 工厂开展测试与试点部署，用于物料和组件搬运等重复性任务。
- BMW 与 Figure 签署多年期 commercial agreement，从小规模原型测试起步，计划逐步扩展到多个工位和工序。

Figure 03 定位为面向家庭和大规模部署的通用人形平台，同样搭配 Helix 控制模型，以执行复杂日常任务[29][32]。

**商业化与融资/团队**

- BMW 多年期 commercial agreement 标志着 Figure 已获得工业客户的实质付费试点订单。
- 多家媒体报道 Figure 获得大量融资并与 OpenAI 建立合作，由 OpenAI 提供多模态模型作为认知层[57]。
- CEO Brett Adcock 为连续创业者，曾创办招聘平台 Vettery 和 eVTOL 公司 Archer Aviation，CTO Jerry Pratt 来自 IHMC，在 bipedal/humanoid 控制方面有深厚积累（相关信息来自二级资料，图谱中未逐条展开，细节不赘）。

### 3.3 1X：家用/安保人形 + Redwood 具身模型

**技术路径**

- 1X 的 Redwood 模型是面向 NEO 家用人形的“突破性 AI 模型”，训练数据来自办公和员工家庭环境中运行的 NEO 机器人，构成多样家庭场景数据集[58][59]。
- Redwood 作为 NEO 的决策与控制核心，通过与自研关节、手爪和传感器深度集成，实现家庭任务中的自主感知和动作控制；训练路径结合模仿学习、远程示教和真实场景数据，并依托云端训练平台[58][59][30]。
- 上层可能集成第三方 LLM 进行语言与对话，但公开资料并未宣称自研通用 LLM[60]。

这一路线可视为“面向家庭场景的端到端具身大模型 + 远程示教 + 云训平台”，聚焦家庭与安保场景。

**产品与落地进度**

- EVE：轮式平台 + 机器人上身，用于安保等场景。
- NEO：全尺寸 general‑purpose humanoid，面向家庭和商业环境，目前处于研发和原型阶段。
- 《纽约时报》和 Freethink 报道指出，1X 人形原型已在少量真实家庭中进行受控试验，执行整理、搬运、基础清洁和陪伴任务，部署形态为小规模试点和受控实验，而非成熟商品。

**商业化与融资/团队**

- 1X 在 2024 年完成 1 亿美元 B 轮融资，投资方包括 OpenAI Startup Fund，资金用于推进 NEO 的开发与部署。
- 作为家用与安保场景玩家，其商业模式以 SaaS + 硬件租赁/订阅为主（细节多来自二级报道，未在图谱中完整展开）。
- 团队规模约百人量级（外部估计），创始人兼 CEO Bernt Øivind Børnich 有机器人和创业背景。

### 3.4 Sanctuary AI：Phoenix 人形 + Carbon AI 认知架构

**技术路径**

- Phoenix 系列人形机器人的认知架构通过现代 AI 技术将自然语言翻译为行动，形成从多模态感知、语言理解到任务规划和动作生成的完整具身链路[61][62]。
- 最新一代 Phoenix 在关节设计、运动范围、视觉和触觉传感等硬件上升级，同时软件栈从传统分层控制演变为更强的大模型驱动和更高程度的端到端控制[63][64]。
- 行业博客称 Phoenix 搭载 Carbon AI 控制系统，用于通用工作场景任务执行，但文章为二手总结，未详述模型内部结构。

**产品与落地进度**

- Phoenix 目标在零售、仓储、工厂等多行业执行补货、拣选、上架等任务，当前商业部署主要为小规模付费试点，而非大规模量产。

**商业化与融资/团队**

- Sanctuary 多轮融资、团队规模数百人（细节多来自通用新闻和投融资数据库，图谱中未逐条给出数值）。
- 联合创始人之一 Geordie Rose 为 D‑Wave 创始人，在量子计算与 AI 创业领域经验丰富（背景为公开常识，此处不扩展）。

### 3.5 Agility Robotics：Digit 仓储 humanoid + 分层控制

**技术路径**

- Digit 的导航和任务执行采用分层软件栈：感知（建图和障碍物检测）、局部/全局路径规划、步态与避障控制等明确分层，非端到端大模型控制[32][33]。
- 在商业部署中，Agility 通过 Arc 工作流控制平台在上层编排仓储和物流任务，与底层控制栈集成，更接近“工业自动化工作流 + 人形本体”的架构[33][34]。

**产品与落地进度**

- Digit 工厂：位于俄勒冈州塞勒姆的 Digit 工厂被称为全球首个高产能人形机器人工厂，自 2024 年开始运行，目标年产数万台 Digit，用于仓储和物流领域。
- Digit 作为双足仓储机器人，已与多家大型零售和物流公司开展 pilot projects，目前仍处试点与小批量部署阶段。

**商业化与融资**

- Agility 获得多轮融资（部分由 NVIDIA 等参与），总融资额在不同报道中存在时间差导致的数值差异（288M vs 640M 美元，分别对应 2024 与 2025 累计），可解释为不同时间点统计而非冲突。
- 商业模式为向仓储和物流客户销售/租赁 Digit + 软件服务。

### 3.6 Apptronik：Apollo 通用人形 + 工业场景

**技术路径**

- Apollo 为全尺寸双足通用人形，定位面向制造、仓储和其他工业环境的多任务执行平台。
- 控制栈由 Apptronik 自研，底层依托 NVIDIA 等算力平台。

**产品与落地进度**

- Apollo 正从原型和小批量阶段向更大规模生产过渡，已在制造和物流领域开展多处 commercial 和 pilot deployments，但仍处预生产/试点阶段。

**商业化与融资**

- Apptronik 获得额外 5.2 亿美元资金，用于扩大 Apollo 生产和商业部署；另一轮 3.5 亿美元融资由 Google 等参与，进一步推高公司估值。
- CNBC 将其视为 Tesla Optimus 的潜在竞争对手。

### 3.7 Boston Dynamics：Atlas + Large Behavior Models

**技术路径**

- Atlas 硬件平台具备高度动态平衡和复杂姿态控制能力，为基于大规模行为模型的自主控制提供基础[65][66]。
- Boston Dynamics 技术博客提出“Large Behavior Models”概念，通过学习多任务行为数据、结合仿真和现实数据，统一生成 Atlas 的全身运动和操作行为，目标构建“AI generalist robots”[67][68]。
- 与 Toyota Research Institute 合作的 AI‑powered robot 实现了自主的全身操控与行走行为，采用统一 AI 控制系统同时处理操控与移动任务[69][70]。

**产品与落地进度**

- 新一代“生产版” Atlas 旨在从研究平台转变为可部署的工业 humanoid，用于制造和物流场景；Hyundai 计划自 2028 年起在工厂部署约 2.5 万台 Atlas。
- 当前（至 2026 年初）仍处开发与测试阶段，量产部署时间点在 2028 年以后。

**商业化与团队**

- Boston Dynamics 已被 Hyundai 收购，后者为其提供资本与产业资源。
- 现阶段商业收入主要来自 Spot 和 Stretch 等产品，Atlas 的商业化仍在规划期。

### 3.8 OpenAI、Google DeepMind 与 NVIDIA：具身智能平台层

**OpenAI**

- OpenAI 不直接生产机器人硬件，而是通过 GPT 系列多模态和语言模型，与 Figure、1X 等合作作为机器人“认知层”。
- Business Insider 报道 OpenAI 已重启机器人研究，建立聚焦 humanoid 的实验室，Sam Altman 认为“humanoid robots moment is coming”，但目前尚未公开面向第三方的具身大模型控制 API，关于统一接口的设想主要来自评论与推测性分析。

**Google DeepMind**

- RT‑1/2 等工作已在前文技术路线中述及[6][9][10][11]。
- Gemini Robotics‑ER 系列被官方定义为“embodied reasoning model”，相当于机器人系统的前额叶皮层，负责高层决策和长时规划，通过视觉和语言等多模态输入输出高层动作计划或子目标，并可跨多种机器人平台复用，实现“一脑多机”[27][31][28]。

**NVIDIA**

- 不直接生产人形整机，而是作为人形机器人生态的平台方：通过 Isaac 仿真平台、人形机器人基础模型、Project GR00T 等，为 Figure、Agility、Apptronik、Boston Dynamics 等提供通用 AI 平台与算力。
- GTC 2024 等活动集中宣传其“humanoid robot platform”计划，强调开发者生态与基础设施角色。

---

## 四、中国代表性公司分析

### 4.1 智元机器人：远征 A1 + “具身智脑”

**技术路径**

- 智元在远征 A1 发布会上提出“具身智脑”概念，将其定义为从感知到动作的全链路智能系统，为通用人形机器人提供统一大脑能力。
- 行业报告将智元方案归类为基于大模型进行世界建模和策略学习的人形机器人代表企业之一。

**产品与落地进度**

- 2023 年发布具身智能通用人形机器人“远征 A1”，定位多场景、多任务应用。
- 券商与行业报告普遍将智元列为国内具身智能通用人形代表企业，后续媒体报道称其在人形机器人产能和出货方面处于国内前列。

**商业化与融资**

- 多份 2024–2026 行业报告和新闻将智元列入全球人形机器人出货量榜首，2027 年全球人形机器人产量约 10 万台的预期中，智元规划年产 10 万台并在 2026 年实现第 1 万台下线（相关数据来自综合报道，图谱中部分以概括形式出现）。  
- 融资方面，公开报道显示智元获得多轮融资，但具体金额与估值在图谱中未完整展示。

### 4.2 宇树科技：四足 + 人形 + 具身模型

**技术路径**

- 宇树官网定位为高性能通用机器人企业，产品覆盖人形、四足以及机器人组件，并提到 2023 年推出配备 4D 激光雷达和“AI 大模型赋能”的 Go2 四足机器人，以及首款通用人形机器人。
- 目标是通过自研机器人本体与具身智能模型结合，实现多形态机器人统一智能控制。

**产品与落地进度**

- 宇树四足机器人在全球出货量达到数万台，人形机器人 H1 等在 2023–2024 年高调亮相，展示多项动态演示。
- 行业报道指出宇树在 2025 年前 3 季度营收超过 10 亿元，盈利数亿元，并计划 IPO，被视为“人形机器人第一股”。
- 2026 年报道和高工产研数据称全球人形机器人出货量前六名均为中国企业，其中包括宇树。

### 4.3 优必选（UBTECH）：Walker 系列 + dual‑loop 工业控制

**技术路径**

- UBTECH Walker 是中国较早实现商业化的双足等身人形机器人之一，公司拥有 2700+ 项机器人与 AI 相关专利，控制重点在硬件与传统控制而非大模型架构。
- Walker S2 在制造业场景采用 dual‑loop AI system，即任务规划层 + 运动控制层的双环路分层控制架构，以提升装配线场景的精度与安全性。

**产品与落地进度与商业化**

- Walker 系列已在教育、政务服务、展览等场景部署多年，并向制造业转型。
- 行业报道称 2025 年优必选全尺寸具身人形机器人销量 1079 台，营收增长 22 倍。

### 4.4 傅利叶智能：康复 + GR‑1 通用人形

**技术路径**

- 在工业具身方案中，傅利叶采用全身动力学动量优化和轨迹规划算法，通过上肢摆臂与步态平衡控制及冗余自由度双臂协同，实现多关节协调控制，偏传统控制和优化路径[37][38]。
- 在 GTC2024 技术文章中，傅利叶明确使用强化学习在仿真环境中训练机器人运动策略（如行走、跑步、跳跃），再迁移到现实机器人，体现“仿真 RL + 动力学控制 + 现实部署”的分层方案[38][39]。

**产品与落地进度**

- 从康复机器人拓展到通用人形 GR‑1，定位为通用人形机器人，强调与 AI 和大模型结合[44][45]。
- 财联社报道 GR‑1 高约 1.65 米、重约 55kg，在展会展示，被列为国内出货预估排名靠前的企业之一[44]。

### 4.5 小米：CyberDog & CyberOne + 自研大模型

**技术路径与产品**

- CyberDog 四足和 CyberOne 全尺寸人形仿生机器人：CyberOne 采用“发达的小脑”和“聪明的大脑”结构，通过全身控制算法协调 21 个关节实现姿态平衡，具备环境语义识别和情绪识别等多模态感知能力，但公开资料未披露是否采用通用大模型或其训练路径。
- 随着小米自有大模型和澎湃 OS 发展，发布会和媒体报道提到正在将大模型能力部署到这些机器人上。

**研发/商业化进度**

- 2025 年新浪科技报道称“CyberOne 即将量产”消息不实，官方否认，表明其仍处研发阶段。
- 2026 年新闻报道“小米人形机器人已在小米汽车工厂上岗作业”，属于内部试点部署而非对外量产。

### 4.6 百度、阿里、华为等平台方

**百度：文心 + 百舸 + “慧思开物”**

- 百度在文心大模型发布会中多次提出“文心赋能机器人、车、设备”等具身方向，被行业报告视为具身智能路线的一部分。
- 百度智能云百舸平台为具身智能提供从仿真、世界模型到策略优化的全栈加速方案，与北京人形机器人创新中心合作。
- 北京人形机器人创新中心 2025 年发布通用具身智能平台“慧思开物”，提出“一脑多能、一脑多机”，由百度智能云提供算力和平台支撑。

**阿里：通义具身团队 + RynnRCP**

- 阿里在 2025 年云栖大会宣布组建机器人和具身智能团队，目标让通义大模型具备驱动实体机器人执行任务的“行动力”，并在软硬件协同和仿真训练方向布局。
- 达摩院开源具身智能“三大件”之一 RynnRCP 机器人服务协议，统一传感器数据采集、模型推理和机器人动作执行流程，为具身智能系统提供标准化上下文协议。
- 阿里云通义千问通过云平台赋能菜鸟物流机器人和合作方硬件，实现“通义 + 机器人/IoT”的组合应用。

**华为：CloudRobo + 盘古 + Ascend**

- 《工业与 AI 融合应用指南》介绍 CloudRobo 具身智能平台：包含“具身规划大模型、具身执行大模型、具身世界大模型和具身工具链”，支持移动底盘、机械臂、复合机器人、四足和人形等多形态机器人。
- Ascend/Atlas 系列为 CloudRobo 提供端‑边‑云一体算力基础，支撑大规模训练与推理。
- 在开发者大会中，盘古大模型与工业机器人、巡检机器人结合的案例展示了“AI+机器人”的工业场景应用。

**其他代表**

- 星动纪元运营的“国地共建具身智能机器人创新中心”在北京亦庄成立，作为人形与具身智能技术的创新平台。
- 李开复及零一万物通过 YI 系列通用大模型和投资/孵化方式，推动“AI 2.0 + 具身智能”的方向，大模型以 API 形式供机器人公司使用。

### 4.7 乐聚、众擎等长尾代表

- 乐聚：教育和人形服务机器人企业，被 Omdia 报告和国内新闻提到为全球人形机器人出货量前几名之一，控制与应用自研，对话能力接入第三方大模型。
- 众擎：主要针对制造和产线的人形机器人公司，在 2025–2026 年全球人形机器人出货量前六中占有一席，面向工业场景自研控制系统并结合第三方模型。

---

## 五、欧洲、日本与以色列代表性公司

### 5.1 PAL Robotics（西班牙）

- 提供 TALOS、REEM‑C、TIAGo++ 等人形与双足平台，广泛用于研发与服务机器人项目[43][71]。
- 自研控制和感知系统，在欧盟研究项目中尝试与视觉和语言模型结合，但市场宣传中较少使用“具身大模型”术语[43][71]。

### 5.2 Engineered Arts（英国）

- 开发高度拟人的人形机器人 Ameca，主要用于展览和接待等场景[72][44]。
- 机器人常集成 OpenAI ChatGPT 等第三方 LLM 进行对话，机械控制层以传统伺服与脚本为主[72][45]。
- 路线可视为“拟人外观 + 对话大模型 + 传统控制”。

### 5.3 日本：Toyota Research Institute、Honda、SoftBank Robotics

- TRI（Toyota Research Institute）：研究型机构，聚焦家务辅助和人机协作机器人，自研感知与控制算法，在与 Boston Dynamics 的 AI‑powered robot 合作中探索统一全身控制与操作的 AI 路线[69][70][46]。
- Honda：以 ASIMO 等早期人形机器人积累闻名，但近年重心更多转向其他业务，具身智能相关对外披露有限[44][46]。
- SoftBank Robotics：通过 Pepper 和 Nao 等服务机器人布局养老和零售场景，对话能力主要接入合作方大模型，机器人本体及低层控制采用传统方案[44][52]。

### 5.4 Mentee Robotics（以色列）

- 行业新闻与 Humanoid.guide 将以色列 Mentee Robotics 视为具身 AI 驱动的人形或腿式机器人初创公司，结合深度学习和大模型进行场景理解与动作生成[72][73]。
- 公共信息有限，技术路线可能包含自研模型与通用 LLM 结合的策略，细节多为媒体推测，需谨慎解读[72][73]。

---

## 六、技术路径对比与软硬件一体化分析

### 6.1 高层“大脑”架构对比

1. **端到端策略大模型路线**  
   - 代表：RT‑1/RT‑2、π₀、部分人形厂商内部策略。  
   - 优点：统一策略，工程简洁；易于多任务扩展。  
   - 缺点：长时序和安全性不足，在高风险工业场景需要配合其他机制[6][9][13][16][17]。

2. **LLM/VLM/VLA + 控制器分层路线**  
   - 代表：EmbodiedGPT、Gemini Robotics‑ER、Figure Helix、Sanctuary Carbon AI、1X Redwood 等[25][27][31][58][61]。  
   - 优点：将高层规划与低层控制解耦，有利于安全性与可解释性；更易跨机器人平台复用（“一脑多机”）[27][31]。  
   - 缺点：系统工程复杂，大模型与控制栈接口设计难度高。

3. **世界模型 + 策略/规划**  
   - 代表：世界模型综述、World Models for VLA Agents、百舸/CloudRobo 的世界模型模块[21][3]。  
   - 优点：样本效率高、可用于安全约束与离线规划；有助于长时序任务。  
   - 缺点：建模误差与计算成本高，工程部署复杂，当前产业应用仍较有限。

### 6.2 控制与本体设计：人形 vs 四足 vs 机械臂

- **人形平台（Figure、Tesla、1X、Sanctuary、Agility、Apptronik、智元、宇树、UBTECH、傅利叶、小米等）**  
  - 关注类人形态、双足行走、上肢灵巧操作，硬件上强调高自由度、关节布局、重量与负载平衡[56][29][65][38][44][44]。
  - 控制路径上既有高度动态控制和 gait 生成（Boston Dynamics、宇树、傅利叶），也有基于大模型的高层策略（Figure、Sanctuary、智元等）[65][37][67]。

- **四足与混合形态（宇树 Go2、CyberDog 等）**  
  - 动态运动与地形适应是核心，强化学习和动力学控制在仿真中扮演重要角色，再迁移到实体机器人[38]。
  - 大模型主要用于语音交互和高层任务理解，低层控制仍以传统方法为主。

- **机械臂 + 仓储/工业场景（Covariant、Digit、Stretch 等）**  
  - 在仓储场景中，多采用“基础模型/brain + 传统工控”的混合路线，如 Covariant Brain 与机械臂控制栈[49]，以及 Digit + Arc 工作流平台[33][34]。

### 6.3 软件架构与基础设施差异

- **云‑边协同程度**  
  - Figure、1X、Sanctuary 等广泛使用云端训练和推理，将计算密集部分放在云侧，机器人侧负责低延迟控制[27][31][58][59]。
  - 工厂/仓储场景中，为降低时延与提高可靠性，部分逻辑必须下沉到边缘侧（Agility、UBTECH、傅利叶等）[32][35][37]。

- **基础设施依赖**  
  - 北美厂商更多依赖 NVIDIA Isaac + Omniverse + Project GR00T 等平台；
  - 中国企业则依托百度百舸、华为 CloudRobo + Ascend、阿里通义云平台等本土基础设施。

---

## 七、产品与商业化进度对比

### 7.1 落地场景与成熟度

综合各公司公开信息，可以按场景与成熟度粗略分层：

1. **工厂/制造业**  
   - Figure 02 在 BMW Spartanburg 工厂试点部署，签署多年商业协议；
   - Tesla Optimus 在自家工厂内部试用（非官方博客消息，未经正式证实）；
   - Boston Dynamics Atlas 规划 2028 年在 Hyundai 工厂部署 2.5 万台；
   - 中国智元、宇树、优必选、傅利叶、小米等在汽车和 3C 工厂开展多种试点和小批量部署。

2. **仓储与物流**  
   - Agility Digit 针对仓储应用，工厂年产目标数万台，已与多家零售/物流企业开展 pilot projects；
   - Apptronik Apollo 面向制造与仓储场景，处于预生产/试点阶段；
   - Covariant 在机械臂仓储自动化领域已有较成熟商业部署[49]。

3. **零售与服务**  
   - Sanctuary Phoenix 在零售门店执行补货、拣选等任务，小规模付费试点；
   - UBTECH Walker、乐聚等在人机交互场景（展览、政务、商场）有多年的商业化经验[50][51]；
   - Engineered Arts Ameca 在展览与接待领域广泛使用[72][45]。

4. **家庭与消费级**  
   - 1X NEO 在真实家庭中进行受控试验，执行家务和陪伴任务，仍属实验性部署；
   - 小米 CyberDog 与 CyberOne 主要用于展示与内部工厂试点，尚未形成大规模消费市场。

总体来看，当前商业化程度最高的场景仍集中在仓储物流、部分制造业和服务/展示领域，真正面向普通家庭的通用人形仍处于试验阶段。

### 7.2 量产与出货规模（重点中国）

- 行业报道与高工产研数据显示，全球人形机器人出货量前六名均为中国企业，包括优必选、乐聚、众擎、傅利叶等。
- 智元在 2026 年实现第 1 万台通用人形下线，规划 2027 年年产 10 万台，被行业报道视为“量产竞赛”的代表。
- 宇树在 2025 年前三季度营收超 10 亿元，盈利数亿元，四足机器人累计出货约数万台，人形出货快速增长。
- 优必选 2025 年全尺寸具身人形机器人销量 1079 台，营收增长 22 倍。

上述数据多数来自综合行业报道和研报摘要，存在统计口径和时间点差异，但共同表明：中国厂商在人形机器人实际出货和营收层面明显领先。

---

## 八、融资、估值与团队格局

### 8.1 北美核心玩家

- **Figure AI**：多轮融资，投资方包括 Parkway Venture Capital、OpenAI、NVIDIA 等，估值在 2024–2025 年间有多次抬升（具体数值因来源差异未在图谱中统一，属于需谨慎比对的信息）。  
- **1X**：2024 年完成 1 亿美元 B 轮融资，OpenAI Startup Fund 等参与。  
- **Sanctuary AI**：多轮融资，获得多家 VC 支持，用于推进 Phoenix 平台和 Carbon AI 控制系统；具体金额与估值未在图谱中完整给出。  
- **Agility Robotics**：到 2024 年总融资约 2.88 亿美元，2025 年有报道称累计约 6.4 亿美元、估值约 21 亿美元，差异主要来自不同时间节点统计。  
- **Apptronik**：获得 5.2 亿美元资金用于扩大 Apollo 生产，并有由 Google 参与的 3.5 亿美元融资轮，估值约 50 亿美元（数值来自新闻报道，需注意随时间变化）。  
- **Boston Dynamics**：被 Hyundai 收购，融资与估值转化为并购对价；  

由于图谱聚焦技术与产品，对各轮融资的细节并未逐一列举，以上为基于新闻报道的总结性描述。

### 8.2 中国公司

- 智元、宇树、优必选、傅利叶、乐聚、众擎等均获得多轮融资，背后有产业资本、地方政府基金与市场化 VC 共同参与。  
- 宇树 IPO 进程推进迅速，被媒体称为“人形机器人第一股”，其招股书展示了年营收超过 10 亿元、盈利数亿元的财务表现。  
- 优必选曾在境外资本市场上市（相关财务信息不在本图谱范围内）。

整体趋势是：北美玩家在融资规模和估值上更集中于少数头部初创公司，而中国厂商则兼具大量中型企业和国资背景平台，资金投入与产业导向紧密结合。

### 8.3 团队背景与人才流动

- 多数北美公司创始人与技术负责人来自 MIT、Berkeley、CMU、IHMC、NASA 等机构，并有 Tesla、Google、OpenAI 等企业背景，这促进了大模型与机器人控制的跨界融合[67][69]。
- 中国厂商的技术负责人普遍来自清华、北大、浙大、哈工大等高校与国家级研究机构，并在机器人控制、伺服驱动、工业自动化等方向积累深厚工程经验[37][38]。
- 平台方（OpenAI、Google DeepMind、NVIDIA、百度、阿里、华为等）的具身团队则汇聚了大模型、分布式训练、仿真和系统工程的人才，推动“具身大模型平台化”。

---

## 九、趋势判断与风险提示

### 9.1 技术趋势

1. **从端到端策略到多模块大模型平台**  
   端到端多模态策略（RT‑1/2、π₀）展示了统一策略的潜力，但在长时序和安全性上仍不足[6][9][13][16]。产业界正快速转向“高层大模型 + 低层控制 + 世界模型 + 工作流编排”的多模块平台化架构（Gemini Robotics‑ER、Helix、Carbon AI、RoboBrain 2.0、CloudRobo、百舸等）[27][31][67]。

2. **“一脑多机”与“多模态多任务”成为主线目标**  
   不论是 Gemini Robotics‑ER、Helix、“具身智脑”、RoboBrain 2.0，还是“慧思开物”“CloudRobo”，其目标高度一致：以一个或少量通用具身模型服务多种机器人形态和任务，实现“一脑多机、一脑多能”[27][31]。

3. **世界模型与安全可控性的结合**  
   世界模型在样本效率、安全性和可解释性方面的优势得到学界重视，但工业界仍处探索期，需要在模型误差与工程复杂性之间取得平衡[21][22][23][3]。

### 9.2 产业与商业趋势

1. **中国在人形量产与出货上的领先**  
   2025–2026 年的多份行业报告显示，全球人形机器人出货量前几名集中在中国企业（优必选、乐聚、众擎、傅利叶、智元、宇树等）。这与中国在消费电子供应链、制造业基础和政策投入上的优势密切相关。

2. **北美在高价值通用人形与家用场景探索领先**  
   Figure、1X、Sanctuary、Agility、Apptronik 等在通用人形和家用场景的技术探索和资本集中度明显更高，重点面向制造业高附加值工位和家庭场景[56][58]。

3. **平台方正在构建“具身智能 PaaS”**  
   OpenAI、Google、NVIDIA、百度、阿里、华为等均在尝试将具身智能能力打包为云平台或开发者平台，通过 API 与 SDK 向机器人厂商开放[10][27]。

### 9.3 风险与不确定性

1. **数据与估值不一致**  
   不同来源对同一公司的累计融资、估值和出货量统计存在差异，如 Agility 的融资总额在不同年份报道中从 2.88 亿到 6.4 亿美元不等。这些差异通常是时间点和统计口径造成的，但在做严谨财务分析时需回到原始报道逐一核实。

2. **二手/推测性技术信息**  
   - Tesla Optimus 的训练路径（如大量 tele‑operation 数据、训练方式完全类比 LLM）主要来自投资者博客和论坛帖，缺乏官方技术文档支撑，可信度有限[54][55]。
   - Sanctuary Carbon AI、部分 OpenAI 机器人实验室细节等，也多由媒体或评论推测。  
   本报告在引用此类信息时已标注来源性质，读者需要结合自身判断使用。

3. **技术落地距离与过度宣传**  
   多家企业在宣传中使用“通用人形”“通用具身智能”等表述，但实际部署常是场景、任务和数量高度受限的试点项目。在评估商业价值时，应区分 demo 与规模化生产/盈利。

---

## 结论

综合上述证据，可以得出以下几点判断：

1. 具身智能的核心共识已经形成：以大规模多模态数据与强表达能力的大模型为中心，结合世界模型、模仿学习、强化学习和传统控制，实现感知—认知—控制—身体的闭环，是通往通用机器人的关键路径[1][2][21]。
2. 技术路线呈多范式并存：端到端策略网络、VLA 具身基础模型、世界模型 + 规划、LLM 驱动模块化系统以及云边协同架构在不同公司和场景中以不同配比组合[6][9][3][25][27][32][37]。
3. 产业格局上，北美企业在“高价值通用人形 + 家用场景 + 云平台”上更为激进，中国企业在人形量产、出货规模和工业场景落地方面领先；欧洲、日本和以色列则在研究型平台和特定场景（研发、展示）保持一定影响力[43][44]。
4. 平台化竞争日趋激烈：OpenAI、Google DeepMind、NVIDIA、百度、阿里、华为等均在构建具身大模型平台与生态，未来整机厂商与平台方的关系将类似“终端 + 操作系统 + 云服务”的新一代生态格局[10][27]。
5. 不确定性主要来自：技术可行性与安全性验证周期、真实商业需求与支付意愿、政策与安全监管，以及当前大量技术细节与财务数据的公开程度不足。对任何单一公司的乐观预期都应基于多源交叉验证的事实，而非仅凭宣传与 demo。

在证据有限和部分数据存在不一致的前提下，本报告尽量基于高可信度的学术文献、权威媒体与公司官方资料给出结构化梳理，并明确标注推测性信息的来源性质，供行业研究者在开展更细致的公司深调和财务建模时参考。

---

## 参考文献

[1] A Comprehensive Survey on Embodied Intelligence https://www.sciopen.com/article/10.26599/AIR.2024.9150042

[2] A Comprehensive Survey on Embodied AI https://arxiv.org/html/2407.06886v8

[3] Populating the World with Optimus Robots - Motley Fool Community https://discussion.fool.com/t/populating-the-world-with-optimus-robots/113044

[4] A Survey of Embodied World Models https://fi.ee.tsinghua.edu.cn/public/publications/0940dda4-af15-11f0-9d60-0242ac120002.pdf

[5] Embodied-World-Models-Survey GitHub repository https://github.com/NJU3DV-LoongGroup/Embodied-World-Models-Survey

[6] Paper List and Resource Repository for Embodied AI https://github.com/HCPLab-SYSU/Embodied_AI_Paper_List

[7] Awesome-Multimodal-Embodied-AI https://github.com/Hoar012/Awesome-Multimodal-Embodied-AI

[8] RT-1: Robotics Transformer for Real-World Control at Scale https://arxiv.org/abs/2212.06817

[9] RT-1 project page https://robotics-transformer1.github.io/

[10] RT-1: Robotics Transformer for Real-World Control at Scale (Google Research Blog) https://research.google/blog/rt-1-robotics-transformer-for-real-world-control-at-scale/

[11] RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control https://arxiv.org/abs/2307.15818

[12] RT-2 project page https://robotics-transformer2.github.io/

[13] RT-2: New model translates vision and language into action (Google DeepMind Blog) https://deepmind.google/blog/rt-2-new-model-translates-vision-and-language-into-action/

[14] π0: Our First Generalist Policy https://www.pi.website/blog/pi0

[15] π₀: A Vision-Language-Action Flow Model for General Robot Control https://arxiv.org/html/2410.24164v1

[16] Strengths, Problems, and the Future of Generalist Robot Policies https://penn-pal-lab.github.io/Pi0-Experiment-in-the-Wild/

[17] EmbodiedGPT: Vision-Language Pre-Training via Embodied Chain of Thought https://neurips.cc/virtual/2023/poster/72127

[18] World Models for Vision-Language-Action Agents https://www.techrxiv.org/doi/pdf/10.36227/techrxiv.176948355.54623875/v1

[19] Spotlight on humanoids: A deep dive into Figure AI https://roboticsandautomationnews.com/2025/05/06/spotlight-on-humanoids-a-deep-dive-into-figure-ai/90373/

[20] Gemini Robotics https://deepmind.google/models/gemini-robotics/

[21] Gemini Robotics 1.5 brings AI agents into the physical world https://deepmind.google/blog/gemini-robotics-15-brings-ai-agents-into-the-physical-world/

[22] Google DeepMind Releases Open X-Embodiment that Includes a ... https://www.facebook.com/groups/DeepNetGroup/posts/2058387294554142/

[23] AI & Robotics | Tesla https://www.tesla.com/AI

[24] Project Go-Big: Internet-Scale Humanoid Pretraining and ... https://www.figure.ai/news/project-go-big

[25] Introducing Figure 03 https://www.figure.ai/news/introducing-figure-03

[26] Redwood AI | 1X https://www.1x.tech/discover/redwood-ai

[27] 1X's NEO humanoid gains autonomy with new Redwood AI model https://www.therobotreport.com/1xs-neo-humanoid-gains-autonomy-with-new-redwood-ai-model/

[28] Sanctuary AI Unveils the Next Generation of AI Robotics https://www.sanctuary.ai/blog/sanctuary-ai-unveils-the-next-generation-of-ai-robotics

[29] About Us - UBTECH Robotics https://www.ubtrobot.com/en/about/company-profile

[30] 阿里通义组建机器人和具身智能团队，要让智能体具备“行动力” https://www.stcn.com/article/detail/3369484.html

[31] Sanctuary AI Unveils Phoenix™ - A Humanoid General-Purpose Robot Designed for Work https://www.sanctuary.ai/blog/sanctuary-ai-unveils-phoenix-a-humanoid-general-purpose-robot-designed-for-work

[32] UBTech: Humanoid robots for the future of manufacturing | Merics https://merics.org/en/comment/ubtech-humanoid-robots-future-manufacturing

[33] 傅利叶发布具身智能工业解决方案，探索未来工厂新形态 https://www.fftai.cn/solutions/21

[34] GTC2024｜助力创新，打造具身时代的开发者平台 https://www.fftai.cn/about-medium-technical/13

[35] 具身智能发展报告 http://www.caict.ac.cn/kxyj/qwfb/bps/202601/P020260130541978285206.pdf

[36] 2025年具身智能行业研究 https://pdf.dfcfw.com/pdf/H3_AP202509041738887829_1.pdf

[37] 30+ Humanoid Robot Companies Ranked [2026] https://blog.robozaps.com/b/humanoid-robot-companies

[38] 21 top companies in the vanguard of the rise of humanoid robots https://rossdawson.com/futurist/companies-creating-future/top-companies-rise-humanoid-robots/

[39] Humanoid Robot Manufacturers https://humanoid.guide/manufacturers/

[40] Digit's Next Steps https://www.agilityrobotics.com/content/digits-next-steps

[41] Agility Robotics Announces New Innovations for Market-Leading Humanoid Robot Digit https://www.agilityrobotics.com/content/agility-robotics-announces-new-innovations-for-market-leading-humanoid-robot-digit

[42] Atlas Humanoid Robot - Boston Dynamics https://bostondynamics.com/products/atlas/

[43] OpenAI Quietly Revives Robotics Ambitions with Secret Lab Focused on Humanoid Development https://www.tekedia.com/openai-quietly-revives-robotics-ambitions-with-secret-lab-focused-on-humanoid-development/

[44] Google DeepMind introduces two Gemini-based models to bring AI to the real world https://www.therobotreport.com/google-deepmind-introduces-two-gemini-models-bring-ai-real-world/

[45] NVIDIA's Humanoid Robot Strategy https://blog.robozaps.com/b/nvidias-next-frontier

[46] 营收已突破10.5亿元！彭志辉：宇树科技是家了不起公司，智元更关注实际生产力价值【附人形机器人行业市场分析】 https://t.qianzhan.com/caijing/detail/260417-a9894d74.html

[47] 智元登顶全球人形机器人出货量榜首 https://auto.gasgoo.com/news/202601/9I70441913C601.shtml

[48] 宇树科技73天过会人形机器人第一股将至- 中国日报网 https://caijing.chinadaily.com.cn/a/202606/02/WS6a1e393ba310942cc49af7f6.html

[49] 传小米人形机器人Cyberone即将量产 消息不实 https://finance.sina.com.cn/tech/roll/2025-03-10/doc-inepeprm3518170.shtml

[50] Boston Dynamics, Google reunite on next-gen Atlas humanoid https://www.therobotreport.com/boston-dynamics-google-reunite-on-next-gen-atlas-humanoid/

[51] Inside OpenAI's renewed push into robotics https://www.businessinsider.com/open-ai-robotics-lab-humanoid-robots-2026-1

[52] 2027年人形机器人产量或达10万台 具身智能“量产竞赛”鸣枪起跑 http://www.cb.com.cn/index/show/jr/cv/cv135256052375

[53] Large Behavior Models and Atlas Find New Footing | Boston Dynamics https://bostondynamics.com/blog/large-behavior-models-atlas-find-new-footing/

[54] AI-Powered Robot by Boston Dynamics and Toyota Research Institute Takes Key Step Towards General ... http://www.tri.global/news/ai-powered-robot-boston-dynamics-and-toyota-research-institute-takes-key-step-towards-general

[55] Unifolm https://www.unifolm.com/

[56] 宇树科技 https://www.unitree.com/cn/

[57] 阿里千问已与均胜电子、宇树和星动纪元等机器人产业链公司合作-AI云资讯 https://www.icloudnews.net/a/108952.html

[58] 百度智能云携手北京人形机器人创新中心助力具身智能产业高质量发展 https://paper.people.com.cn/rmrb/pc/content/202505/29/content_30076067.html

[59] 具身智能竞速时刻，百度百舸提供全栈加速方案 https://www.geekpark.net/news/352666

[60] 阿里通义组建机器人和具身智能团队，要让智能体具备“行动力” https://www.jiemian.com/article/13435503.html

[61] 达摩院开源具身智能“三大件”，机器人上下文协议首次开源 https://www.qbitai.com/2025/08/320807.html

[62] 工业与AI融合应用指南 https://www-file.huawei.com/dam/asset/view/dda7ee674ced41d4bb989b365ea0a028.pdf

[63] 昇腾计算-华为Ascend-AI计算 https://e.huawei.com/cn/products/computing/ascend

[64] 具身智能即将为通用机器人补全最后一块拼图 https://www.agibot.com/article/188/detail/7.html

[65] CyberOne全尺寸人形仿生机器人 https://www.mi.com/cyberone

[66] Humanoid Robots for BMW Group Plant Spartanburg. https://www.bmwgroup.com/en/news/general/2024/humanoid-robots.html

[67] BMW will deploy Figure’s humanoid robot at South Carolina plant https://techcrunch.com/2024/01/18/bmw-will-deploy-figures-humanoid-robot-at-south-carolina-plant/

[68] BMW taps humanoid startup Figure to take on Tesla's robot https://www.reuters.com/business/autos-transportation/bmw-taps-humanoid-startup-figure-take-teslas-robot-2024-01-18/

[69] 1X Technologies raises $100M Series B to advance NEO humanoid robot https://www.therobotreport.com/1x-technologies-raises-100m-series-b-advance-neo-humanoid-robot/

[70] Invasion of the Home Humanoid Robots https://www.nytimes.com/2025/04/04/technology/humanoid-robots-1x.html

[71] Gemini Robotics brings AI into the physical world https://deepmind.google/blog/gemini-robotics-brings-ai-into-the-physical-world/

[72] Google’s Gemini Robotics AI Model Reaches Into the Physical World https://www.wired.com/story/googles-gemini-robotics-ai-model-that-reaches-into-the-physical-world/

[73] Humanoid robotics developers must pick which problems to solve, says NVIDIA https://www.therobotreport.com/humanoid-robotics-developers-must-pick-which-problems-solve-says-nvidia/
