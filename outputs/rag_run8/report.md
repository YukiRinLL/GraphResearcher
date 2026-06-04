# 引言

## 0.1 具身智能的定义与本报告范围

学术综述普遍将具身智能定义为“在真实世界场景中集成感知、认知和行为的智能系统”，要求系统通过“身体”与物理世界交互，将感知、认知与执行闭环起来。[1][2] 有研究以“感知‑认知‑行为（Perception‑Cognition‑Behavior, PCB）”三层框架刻画具身智能，并提出面向未来的 Large PCB 模型。[2]

产业侧的白皮书和报告则从“物理 AI”的角度，将具身智能视为多模态感知（视觉、语言、触觉等）、端到端决策、物理交互和智能体协同的结合体，强调多模态具身大模型和世界模型作为基础设施的作用。[3][4]

在产品载体上，报告认为具身智能当前主要体现在：[4][5][6]

- 人形机器人（双足）  
- 四足机器人（巡检、安防）  
- 轮式底盘 + 机械臂的协作/服务机器人  
- “机器人+大模型”的具身智能体与具身大模型系统  

本报告的范围与假设：

- 时间：聚焦 2020–2026 年，参考若干发展报告与市场研究的时间划分。[4][6][7][8]  
- 对象：围绕具身智能的技术路线、人形/四足/服务机器人及“机器人+大模型”系统，重点关注 Figure AI、Agility Robotics、Tesla、1X、Apptronik、Boston Dynamics、Unitree、UBTECH 等在全球人形/具身智能赛道中的代表性企业。[9][10][11]  
- 维度：技术路线及系统架构；按路线划分的代表性公司及技术路径；产品形态与产品/商业化进度；融资情况与资本格局；团队与人才背景；综合趋势判断。  
- 地域：从全球视角分析技术路线与代表性公司，对中国在应用与政策方面的情况作必要补充。[4][5][6][12][13]

## 0.2 产业阶段与典型应用场景

多份产业报告指出，自 2020 年以来具身智能进入“模型+本体+场景”协同发展阶段：人形、四足和协作机械臂厂商陆续启动具身智能化升级。[4][6][7] 大致阶段为：

- 2020–2022：以实验室 demo、展会展示和少量 B 端试点为主。[4][6][14]  
- 2023–2024：部分企业在工业与物流场景开展有偿试点和小批量生产试点。[4][6][7][8]  
- 2025–2026：部分龙头企业进入“预量产/量产”阶段，多份报告认为 2026 年前后有望成为人形机器人大规模部署的拐点。[4][7][8]

典型应用场景包括：[4][5][6][7][15][16]

- 工业制造：3C、汽车零部件、机加工等柔性生产场景  
- 物流与仓储：仓库搬运、拣选、电商仓储  
- 商用服务：展厅导览、商场服务与安防  
- 安防与巡检：园区、港口与能源、电力设施巡检  
- 医疗与养老：病房巡检、康复辅助与护理试点  
- 家用与陪伴：仍处高价试点与概念阶段  

在中国，清洁和部分商用服务机器人已实现“量产+规模化部署”，人形机器人多处于前量产或小批量试点；四足机器人在安防与巡检中已有典型项目，但整体订单量仍有限。[5]

## 0.3 方法来源与局限性

本报告基于以下类型证据：

- 官方/行业报告与白皮书[3][4][6][7][8][12][13]  
- 学术论文与技术综述[1][2][17][18][19][44][45]  
- 企业官网、技术博客与案例材料[20][21][22][23][24][25][76][81]  
- 行业榜单、能力对比表和市场新闻[9][10][11][26][27][72][73][83]  

局限性说明：

- 部分初创公司（如银河通用、它石智航、OriginFlow、星海图、智平方、智元等）的融资与团队信息在本次图谱中缺乏系统数据；  
- 对 Tesla Optimus 等关键公司产量与时间表，不同来源存在“官方规划 vs 第三方估算”的差异；[57][58]  
- 多数公司对内部软件堆栈和模型细节披露有限，技术路线分析主要基于公开表述和典型系统，而非完整内部实现。

后文如遇明显口径差异或信息缺口，将在正文中直接标注。

---

# 第一章 全球具身智能的主要技术路线

## 1.1 技术路线分类口径

中国信通院《具身智能发展报告》将具身智能技术路径划分为四条主线：[6][28]

1. **模块化分层路线**：传统感知‑规划‑控制（P‑P‑C）模块化体系，引入深度学习改善感知与局部策略。  
2. **分层大模型路线**：在高层规划和任务分解中使用大语言/多模态模型，底层保留传统控制或 RL 策略。  
3. **端到端大模型路线**：以视觉‑语言‑动作（VLA）或具身大模型从多模态输入直接输出动作。  
4. **世界模型路线**：学习环境内部模型进行长时预测和规划，结合策略优化实现控制。

工业界技术文章则常采用“三条路线”的划分：[30]

1. 传统模块化路线（感知‑规划‑控制分离）  
2. 大模型增强分层路线（LLM/LVLM + 技能库/底层控制）  
3. 端到端大模型/世界模型路线（VLA 与世界模型合并归类）

大模型赋能具身智能的综述从“决策+学习”的角度，将技术拆为：  
- 自主决策：分层决策 vs 端到端决策；  
- 具身学习：模仿学习、强化学习及混合范式；  
并将世界模型视为支撑组件而非单独路线。[17][18][31]

IEEE 综述《Embodied AI: From LLMs to World Models》则将具身 AI 总结为两个方向：[19]

- LLM/多模态 LLM 驱动的具身 AI  
- 世界模型驱动的具身 AI  

并提出“MLLM + 世界模型联合驱动”的长期架构。

综合来看：

- 分类差异主要在于：是否将世界模型单列、如何刻画大模型在系统中的层级角色；  
- 对“传统模块化 + 大模型增强分层 + 端到端/世界模型”为主轴的共识高度一致。

## 1.2 模块化分层路线

模块化分层路线延续传统机器人工程实践，在感知、规划与控制各模块内引入深度学习，但维持清晰的模块边界。[6][28][29]

典型特征：

- 感知：视觉/激光雷达等多源传感器 + 深度学习用于检测、识别与状态估计；  
- 规划：任务规划与运动规划，往往带有规则或优化求解器；  
- 控制：低层伺服和轨迹控制，强调稳定性与安全性。[6][29][32]

医疗机器人系统综述显示，多数具身 AI 医疗机器人采用“视觉感知 + 深度学习 + 强化学习/策略优化 + 执行器”的模块化体系，用于远程临场、康复和院内物流等场景。[32][33]  
NEC Labs 的 Embodied AI 项目也是代表：通过构建场景拓扑图结合导航与运动策略，在真实环境中完成长程任务。[33][34]

优势与适用性：

- 在安全性与可解释性要求极高的医疗、工业等领域仍是主流；  
- 较易集成成熟的工业控制与安全标准，缺点是工程集成复杂、端到端优化能力有限。

## 1.3 分层大模型路线（大模型增强分层）

分层大模型路线结合大语言/多模态模型与传统控制，实现“语义决策 + 安全执行”的折中。[6][17][18][24][35]

典型架构：

- 高层：LLM/LVLM 负责指令理解、任务分解与计划生成；  
- 中层：技能选择与调度（技能库由模仿学习或 RL 训练得到）；  
- 低层：控制器或低维策略网络输出关节控制与接触控制。

代表系统与公司：

- **PaLM‑E**：Google 提出的多模态 LLM，将机器人和环境信息编码进 LLM 进行决策，高层规划与下游控制解耦。[24][40][41]  
- **ChatGPT for Robotics（Microsoft）**：LLM 生成控制代码或脚本调用机器人 API，属于“LLM+技能库”的分层范式。[24][35]  
- **Gemini Robotics‑ER 等**：通过 Gemini 类大模型负责规划，再调用机器人控制模块执行。[6][28][43]  
- **智元机器人 EI‑Brain**：云‑端‑场景多级“超脑/大脑/小脑/脑干”架构，是中国在分层大模型路线上的代表工程实现。[24][39]

优点：  
- 兼顾语义理解与工程安全，较容易接入现有机器人控制系统；  
- 技能库可复用与扩展。

局限：  
- 技能覆盖与可组合性成为瓶颈；  
- 系统复杂度高，对工程团队能力要求高。

## 1.4 端到端具身大模型与 VLA 路线

端到端路线试图用一个多模态大模型从感知到控制全过程映射。[6][17][18][31]

代表系统：

- **RT‑1**：基于多机器人和 13 万+轨迹数据训练 Transformer 策略网络，实现多任务模仿学习。[24][40]  
- **RT‑2**：在 RT‑1 基础上融合互联网视觉‑语言数据和机器人轨迹，形成 VLA 模型，能从图像和文本直接生成动作 token，并展示一定的跨物体泛化和推理能力。[24][41]  
- **Octo**：使用扩散模型输出连续动作，在具身决策中代表“扩散策略网络”路线。[18][31]  
- **1X World Model**：以视频为输入构建世界模型，从视频到动作统一建模，服务于 1X 人形机器人。[22][49]

产业评估指出，尽管端到端 VLA 在概念上完成“感知‑决策‑执行”闭环，但当前系统在工程上存在明显不足：[6][28][42][43]

- 对训练分布外场景的泛化能力不足；  
- 与特定本体高度绑定，跨平台迁移困难；  
- 在整理垃圾、物品交换等长程多步骤任务上的成功率多数仅为 20–40%。

因此，端到端具身大模型目前更多作为研究方向和特定场景的增强模块，而非普适、唯一的工程解法。

## 1.5 世界模型路线与“LLM+WM 联合”

世界模型路线通过学习环境的内部动力学模型支持多步预测和规划。[18][19][44][45]

功能特征：

- 对未来状态进行预测；  
- 学习紧凑的状态表示；  
- 通过规划与策略优化提升数据效率；  
- 支撑 sim‑to‑real 迁移与安全验证。

典型系统与资源：

- **Physical Intelligence π 系列**：作为世界模型驱动路线的代表之一，被信通院报告专门讨论。[6][28]  
- **Dreamer 系列**和一系列深度世界模型：用于在潜在空间中学习策略。[44][45]  
- **NeBula、UniSim、RobotDreamPolicy、DayDreamer、SWIM、SynthER、MTDiff、VPDD** 等项目构成世界模型与具身学习的丰富生态。[18][31][44][46]

IEEE 综述指出：MLLM 在语义推理与任务分解方面强，世界模型在物理一致性与长时预测方面强，两者结合是实现高性能具身智能的关键。[19]

## 1.6 强化学习与模仿学习的融合范式

大模型赋能具身智能的综述将具身学习归纳为：模仿学习（IL）、强化学习（RL）、人类反馈 RL（RLHF）、扩散策略网络等。[17][18][31]

工业与学术分析中出现的共识：[17][18][31][47][48]

- 大量公司在当前阶段以模仿学习/行为克隆为主，特别是人形机器人灵巧操作；  
- 强化学习在复杂操作和仿真训练中作为性能和泛化增强手段；  
- 世界模型与视频模型通过生成或增强数据，潜在帮助降低真实交互数据需求；  
- 未来路线倾向于“IL + RL + 世界模型 + 大模型”组合，而非单一范式。

---

# 第二章 按技术路线划分的代表性公司与技术路径

需要强调：大多数公司采用混合架构（例如“分层+端到端”“世界模型+传统控制”），本章归类以公开主线特征为依据，难以反映内部全部实现细节。

## 2.1 Google/DeepMind：分层大模型 + 端到端 VLA 的综合路线

产业综述将 Google 路线描述为同时推进分层大模型与端到端 VLA：[24][40][41]

- **PaLM‑E**（分层大模型）：  
  - 模型将多模态信息编码进 LLM，实现高层规划与语义决策；  
  - 具体关节控制由下游控制器完成。

- **RT‑1/RT‑2**（端到端 VLA）：  
  - RT‑1：多任务模仿学习策略网络；  
  - RT‑2：融合互联网与机器人数据的 VLA 模型，从图像与文本直接输出动作 token。[24][40][41]

- **RoboCat**（IL+数据增强）：  
  - 通过专家示例和合成数据构建跨任务、多本体控制模型，实现一定的泛化能力。[24][41]

综合判断：Google 路线覆盖分层与端到端两条主线，是具身大模型方向的学术/产业标杆。

## 2.2 分层大模型路线代表：Microsoft、智元机器人、Gemini Robotics

### 2.2.1 Microsoft ChatGPT for Robotics

基于公开技术说明和行业综述，ChatGPT for Robotics 的模式是：[24][35]

- LLM 解析自然语言指令，生成机器人控制代码或高层任务脚本；  
- 这些脚本调用已有技能与控制 API；  
- 底层执行由传统控制与安全层负责。

路线特征：典型“大模型在计划层+技能库”的分层方案。

### 2.2.2 智元机器人 EI‑Brain

AGIBOT 的技术综述将智元 EI‑Brain 描述为多层架构：[24][39]

- 云端“超脑”：负责复杂任务规划与知识推理；  
- 端侧“大脑”：进行任务与技能级语义推理与编排；  
- “小脑”：在特定场景生成具体运动指令；  
- “脑干”：承担伺服与电机控制。

该架构完全符合“分层大模型+技能库+传统控制”的范式。

### 2.2.3 Gemini Robotics‑ER 等

信通院报告将 Gemini Robotics‑ER 视为分层大模型路线代表之一：大模型负责规划，控制模块负责执行。[6][28][43]  
对整理垃圾、物品交换等长程任务实验表明，其成功率仍仅 20–40%，显示该路线在长程任务上仍有显著提升空间。[6][43]

## 2.3 端到端具身大模型/VLA 路线代表：RT‑1/RT‑2、Octo、1X World Model

- **RT‑1/RT‑2**：作为端到端 VLA 模型代表，展示了在多任务、多物体场景中的泛化能力。[24][40][41]  
- **Octo**：扩散策略网络路线代表，用扩散过程直接生成动作，融入具身决策中。[18][31]  
- **1X World Model**：1X 将其作为核心技术之一，“从视频到动作”学习世界模型和策略，实现对 EVE/NEO 等平台的控制。[22][49]

信通院报告以 1X World Model 和 Physical Intelligence π 为例说明当前端到端 VLA/世界模型在陌生物体和复杂任务中的性能不足。[6][28][42]

## 2.4 世界模型与“机器人大脑”路线代表：Physical Intelligence 等

Physical Intelligence 被 Crunchbase 报道为“机器人通用大脑”公司，2024 年获得约 4 亿美元融资，对应约 20 亿美元估值，用于构建通用机器人“大脑模型”和推进从实验向商业部署的转化。[50][51]

信通院报告中，Physical Intelligence π 系列被作为世界模型路线的典型系统，强调其在环境建模和长时预测方面的代表性，同时指出在操作陌生物体或目标遮挡任务中成功率仍有限。[6][28][42]

整体来看，“机器人大脑/世界模型平台”路线强调软硬件解耦，试图为不同机器人提供统一决策大脑。

## 2.5 行为克隆主导的人形机器人公司：Tesla、Figure 等（公开信息有限）

研究随笔及行业文章指出，目前许多人形机器人公司在灵巧操作方面仍以行为克隆为主线：通过 VR/动捕采集人类操控数据，训练网络模仿操作。[47][48]

- Tesla Optimus：  
  - 利用 Tesla 现有 AI 基础设施，包括 FSD 网络与 Dojo 等算力，用于学习机器人控制。[59][60]  
  - 公开演示中展示通过模仿学习完成折衣服等任务。[57][60]

- Figure AI：  
  - 大量演示视频展示“整理、搬运、工作站操作”等，行业讨论普遍认为其采用行为克隆+大模型规划的组合，但缺乏详细技术白皮书。[47][52][53]

由于公司对具体架构（端到端 vs 分层 vs 世界模型混合）的披露有限，本报告仅能基于“行为克隆为主线”的公开资讯进行定性判断，不对内部算法细节做推断。

## 2.6 典型公司技术路线概览（基于公开信息）

在不超出证据前提下，可以形成粗粒度映射：

- **Google/DeepMind**：分层大模型（PaLM‑E/ChatGPT for Robotics）+ 端到端 VLA（RT‑1/RT‑2）+ IL/数据增强（RoboCat）。[24][40][41]  
- **1X**：世界模型驱动（1X World Model）+ 端到端学习，支撑 EVE/NEO 等人形机器人。[22][49]  
- **Physical Intelligence**：世界模型/机器人“大脑”平台，侧重于环境建模和通用控制。[6][18][50]  
- **智元机器人**：分层大模型+技能库路线（EI‑Brain 架构）。[24][39]  
- **Gemini Robotics**：分层大模型 + VLA 组合，在长程任务上仍有明显局限。[6][28][43]  
- **Tesla、Figure、Agility、Unitree、UBTECH、Apptronik 等**：普遍被认为采用“传统控制/分层 + 模仿学习（行为克隆）+（可能的）大模型增强”组合，具体技术堆栈公开细节不足，仅能通过产品表现和部分技术合作信息间接推断。[9][11][21][47][48][76][81]

---

# 第三章 代表性公司产品形态、产品进度与商业化落地

本章重点从“公司‑产品线‑阶段‑场景”的角度梳理进度。由于部分公司未公开精确出货量或订单数，以下仅在有明确数据时引用数值。

## 3.1 Figure AI：通用人形机器人平台

Figure AI 被 EVST、Robozaps 等多份榜单列为 Top 级人形机器人公司之一。[9][11]

- **产品形态**：通用人形机器人（Figure 02/03），面向工业和物流场景。[9][11][52]  
- **场景**：面向工厂和仓储的搬运和协作作业，被多份市场研究视为潜在主要落地方向。[27][50]  
- **阶段**：  
  - 2022–2024：技术展示和试验阶段为主；  
  - 2025–2026：被纳入全球商业人形机器人市场核心参与者，但公开资料对具体量产节点和交付规模未给出统一数据。[27][50][52][53]

## 3.2 Agility Robotics：Digit 在工业/物流场景的迭代

Agility Robotics 是最早将人形机器人推进工业和物流场景的公司之一。

- **产品**：Digit 人形机器人。[9][10][26]  
- **技术与能力**：New Market Pitch 的对比表显示 Digit 在行走、搬运、持久运行等能力上表现成熟，被视为“生产环境可用”级别。[26][54]  
- **场景与客户**：  
  - 与 Toyota Motor Manufacturing Canada (TMMC) 签署商业协议，在安大略工厂部署 Digit 执行物流与搬运任务。[20][55][56]  
  - 早前与 Amazon/GXO 等在仓储场景试点合作（见行业报道，图谱中有引用）。[21][74]

- **阶段**：  
  - 2020–2022：演示与少量试点；  
  - 2023–2024：在工业和物流场景进行有偿试点与小批量部署；  
  - 2025–2026：通过与 Toyota 等合作迈向“预量产/规模化部署”。

## 3.3 Tesla：Optimus 通用人形机器人

Tesla 的 Optimus 在多份榜单中被列为通用人形机器人代表。[10][11][26]

- **产品形态**：Optimus Gen 2/Gen 3，被定位为通用人形平台，目标是协助工厂工作并最终进入家庭场景。[57][60][62]  
- **技术堆栈**：利用 Tesla 在自动驾驶上的 FSD 网络和 Dojo 训练基础设施，训练机器人控制模型。[59][60]  
- **内部试点与产量**：  
  - 官方表述：计划在 2025 年前后在工厂内部大量试用，并逐步扩展应用。[57][61][62]  
  - 第三方估计：有分析认为 2025 年目标为 5,000 台内部部署，但实际产量可能仅为数百台（约 300 台），两者存在不小差距。[57][58]  
  由于缺乏权威统计，本报告将产量数字视为“目标与非官方估计”，不作确定性结论。

总体看，Optimus 在技术与品牌上有强号召力，但其商业化仍处于内部试用和预量产阶段，外部付费客户的部署情况尚不透明。

## 3.4 1X Technologies：EVE（企业场景）与 NEO/NEO Beta（家庭场景）

1X 被列为 2026 年值得关注的人形机器人公司之一。[9][11][65]

- **产品线**：  
  - EVE：面向安全与企业环境的人形机器人。  
  - NEO/NEO Beta：面向家庭的双足人形机器人，官方宣布将开展家庭试点。[23][63][64]  

- **技术路线**：以 1X World Model 为核心，从视频到动作学习策略，是端到端世界模型路线代表。[22][49]  

- **商业化阶段**：  
  - EVE：已在企业场景以订阅/服务方式部署（例如安防场景）。  
  - NEO Beta：正在准备家庭场景试点，仍处早期阶段。[23][63][64][65]

1X 在“家用人形+世界模型”的探索上走在前列，但家庭场景整体仍处于可控试点期。

## 3.5 Apptronik：Apollo 与制造场景

Apptronik 的 Apollo 是人形机器人商业化的代表之一。[10][11]

- **产品**：Apollo，被定位为面向制造与服务场景的人形平台。[66][67]  
- **合作与场景**：  
  - 与 Mercedes‑Benz 达成商业合作，使 Apollo 在汽车制造工厂执行重复、劳动密集型任务。[67]  
  - 与 Jabil 合作以规模化生产 Apollo 并在其制造运营中部署。[68]  
  - NASA Spinoff 报告将 Apollo 视为“协助装配线的人形机器人”示例。[70][71]

- **阶段**：  
  - 2023–2024：demo 与试点项目为主；  
  - 2025–2026：通过与 Jabil 等的合作布局量产能力，进入小批量生产与商业部署阶段。[68][69][70]

## 3.6 Boston Dynamics：Stretch、Spot 与 Atlas

Boston Dynamics 在具身智能产业中扮演“工程标杆”角色。

- **Stretch（物流机器人）**：[72][73][74]  
  - 面向仓储与物流的箱体搬运机器人；  
  - 2023 年起对外销售，“now available for commercial purchase”；  
  - Otto Group 等客户在 20+ 设施部署 Stretch 和 Spot，说明其已进入规模化商业应用阶段。[74]

- **Spot（四足巡检机器人）**：[73][74]  
  - 在工业设施与仓储环境中执行巡检与数据采集；  
  - 成为安防与能源/电力巡检中具身机器人的典型代表。

- **Atlas（人形平台）**：[75]  
  - 电驱人形机器人平台，主要用于技术探索与演示；  
  - 尚未像 Stretch 那样形成商业量产。

总体上，Boston Dynamics 在“物流与巡检”场景已实现成熟商业化，人形方向仍侧重技术示范。

## 3.7 Unitree：四足机器人与人形 G1/H 系列

Unitree 是中国在具身机器人方向的代表企业之一。[12][76][77]

- **产品线**：  
  - Go2 四足机器人：被描述为 “New Creature of Embodied AI”，强调具身智能属性；[76][77]  
  - 人形 H1/H2/H2 Plus；  
  - G1：被称为 “Humanoid agent AI avatar”，强调其作为具身 AI 代理输出的属性。[76][77]

- **量产与销量（存在口径差异）**：  
  - 新闻稿称 Unitree 2025 年人形机器人出货量超过 5,500 台，位列全球第一；[78]  
  - 随后公司发布澄清公告，对具体销售数据进行更细致说明，表明原报道中某些数字存在需解释之处。[79]  
  因此在引用销量数据时，应将其视为“公司对外口径+后续澄清”，而非权威统计。

Unitree 以擅长运动控制和硬件一体化著称，其在具身大模型与 VLA 方向的公开说明相对有限。

## 3.8 UBTECH：Walker 系列与订单规模

UBTECH（优必选）在服务和教育机器人方向布局多年。

- **产品线**：[81][82]  
  - Walker X/S 系列：商业人形服务机器人；  
  - Cruzr 系列：商用服务机器人；  
  - Alpha 系列：教育/消费级机器人。

- **商业化进度**：  
  - 报道称 Walker S2 开始量产和交付，订单金额超过 8 亿元人民币，并规划 2025 年年产能 500 台、2026 年 5,000 台、2027 年 10,000 台。[83]  
  - 在中东等地展会展示人形机器人与解决方案，表明其已有海外拓展。[84]

UBTECH 在服务型人形机器人商业化方面处于领先位置，但其内部智能堆栈（是否采用具身大模型、世界模型等）公开细节有限。

## 3.9 其他重要人形/具身机器人公司概览

多个榜单和市场研究将如下公司纳入“全球商业人形机器人主要参与者”：[10][11][26][27]

- Sanctuary AI – Phoenix  
- Engineered Arts – Ameca  
- Hanson Robotics – Sophia  
- 小米 – CyberOne  
- Fourier Intelligence – GR‑3  
- XPeng Robotics – IRON  
- AgiBot – A2 Ultra  
- Leju Robotics 等  

这些公司在人机交互、展览展示、工业与家庭场景等方向进行探索。由于图谱中未收集到系统的产品迭代、大规模部署与融资数据，本报告仅将其作为赛道参与者列出，不展开详细进度对比。

---

# 第四章 融资情况与资本格局

## 4.1 全球资本投入概况

一份针对 2025–2030 年的市场研究指出：[27][85][86]

- 2025 年全球商业人形机器人市场收入约 9 亿美元；  
- 双足人形机器人出货量约 8,000–16,000 台；  
- 人形机器人领域投资资本约 40–50 亿美元，投资与收入比约 4–5:1。  

这表明人形机器人产业处于“高投入、早期商业化”阶段。

Crunchbase 对 2024 年机器人创业公司融资的统计进一步显示：[50]

- 2024 年面向机器人和机器人 AI 模型的创业公司获得约 72 亿美元融资；  
- 资金集中流入通用人形机器人和“机器人通用大脑”方向。

## 4.2 国际代表性公司融资情况

### 4.2.1 Figure AI

Crunchbase 报道中给出的关键信息：[50][51]

- 成立时间：2022 年；  
- 2024 年获得 6.75 亿美元 B 轮融资；  
- 用途：从实验原型向商业化部署过渡，建设生产线，推进在工厂和仓储场景的试点与初步商业化；  
- Figure AI 被多个市场研究与榜单列为全球商业人形机器人核心参与者。[9][11][27]

关于 Figure 的 C 轮及总融资额，在部分外部数据库中存在 10 亿美元 vs 10 亿+美元、17.5 亿 vs 19 亿等口径差异；这类细节未在本次图谱中统一校验，报告不做具体推断。

### 4.2.2 Physical Intelligence

同一篇 Crunchbase 报道指出：[50][51]

- 公司定位：构建机器人通用“大脑模型”的 AI 初创企业，侧重世界模型与具身智能；  
- 2024 年融资约 4 亿美元，对应约 20 亿美元估值；  
- 资金主要用于研发世界模型与推进其在各类机器人平台上的商业化部署。

### 4.2.3 Skild AI

Crunchbase 还提到：[50]

- Skild AI 总部位于匹兹堡；  
- 专注机器人通用“大脑模型”；  
- 2024 年获得 1.5 亿美元早期融资，用于构建可迁移到多机器人平台的 AI 模型。

### 4.2.4 其他国际公司

市场研究与榜单将以下企业列为商业人形机器人市场的关键参与者：[11][27][86]

- Figure AI、Agility Robotics、Tesla、UBTECH、Boston Dynamics、Apptronik、AgiBot、Unitree、Leju 等  

但本次图谱对其中大多数公司的融资轮次、金额和估值未做系统抽取，因此报告仅将其作为“重要参与者”呈现，不构造未经证实的融资表。

## 4.3 中国具身智能/人形机器人资本格局（公开数据不足）

中国层面：

- 国家将“具身智能”纳入国家战略重点方向，多份政策文件强调支持具身智能与人形机器人产业发展。[12][13][80]  
- 地方政府推动在工业园区、港口和仓储基地进行具身智能机器人示范应用。[12]

关于银河通用、它石智航、OriginFlow、星海图、智平方、智元机器人、宇树科技等公司的具体融资轮次与估值：

- 本次图谱仅有少量零散线索，未形成交叉验证的数据集；  
- 部分报道的来源可信度有限或缺乏权威媒体与企业信息平台的佐证；  
- 因此，本报告不列出不完整或口径不明的融资数字，仅将这些企业理解为“活跃的具身智能/人形机器人创业公司群体”。

## 4.4 资本对技术路线的偏好

现有证据显示，资本在技术路线上的偏好呈现两个方向：[27][50][51][86]

1. **垂直一体化人形/具身机器人公司**  
   - 代表：Figure AI、Agility、Apptronik、Unitree、UBTECH 等；  
   - 路线：重视“本体+具身智能模型+场景解决方案”的一体化能力；  
   - 投资逻辑：押注于“软硬结合+场景先行”的商业落地能力。

2. **“机器人大脑/世界模型”平台公司**  
   - 代表：Physical Intelligence、Skild AI 等；  
   - 路线：通过世界模型和具身大模型向多家 robot OEM 输出统一“大脑”；  
   - 投资逻辑：押注于软件与模型的可复用性与平台化潜力。

同时，部分科技巨头（Alphabet 等）通过 CVC 参与人形机器人和具身智能公司的融资，体现出“技术协同+战略布局”的动机。[50][68]

---

# 第五章 团队与人才背景

## 5.1 整体人才结构与来源

学术与产业报告在宏观层面指出：[3][6][12]

- 具身智能涉及机器人、控制、计算机视觉、自然语言处理、强化学习和世界模型等多学科；  
- 人才主要来自顶尖高校与研究机构的机器人与 AI 方向，以及头部科技公司与自动驾驶公司；  
- 中国通过高校‑科研院所‑企业联合培养推动具身智能人才体系建设。

然而，多数公开材料聚焦技术与产品，对团队结构与核心成员背景披露有限。

## 5.2 代表性公司团队信息（公开维度）

- **Figure AI**：图谱中收录的公司概览指出其位于硅谷，由具机器人和自动驾驶背景的创业团队创建，但未收录详细创始人与高管简历，因此无法给出精确团队构成。[52][53]  
- **Physical Intelligence、Skild AI**：Crunchbase 报道强调其创始团队由具身智能和机器人 AI 研究人员组成，但未展开细节。[50][51]  
- **国内企业（Unitree、UBTECH 等）**：公开资料更侧重公司产品和市场表现，对核心技术团队背景多以“机器人与 AI 专家团队”等概述呈现。[76][81][82]

关于 OriginFlow 等“00 后团队”创业公司，本次图谱中未收录权威来源，因此本报告不做具体陈述。

## 5.3 人才与生态建设的结构性问题

现有综述与报道指出：[1][3][6][18][44][45][46]

- 真正掌握“机器人+大模型+世界模型+控制”全栈能力的人才仍较稀缺；  
- 行业高度依赖开源生态（如 Embodied AI Paper List、世界模型工具链等）和仿真平台支持；  
- 标准化接口、任务基准和评测平台仍在建设中，这也加大了跨公司人才流动与知识复用的难度。

总体而言，人才维度的信息不透明是现阶段进行公司深度比较时的一大限制因素。

---

# 第六章 综合评估与趋势判断（2020–2026）

## 6.1 各技术路线的成熟度与适用场景

结合前文分析，可以对 2020–2026 年各技术路线的阶段作如下判断：

- **模块化分层**：  
  - 工程成熟度最高，广泛应用于工业、医疗和成熟场景；[4][6][15][32]  
  - 在安全性与标准化要求高的场景（如医疗、重工业）短期内难以被完全替代。  

- **分层大模型**：  
  - 已在大厂与头部企业广泛试水，通用执行模型与 EI‑Brain 等架构形成了一套可复用思路；[24][37][39]  
  - 在“自然语言指令 → 任务分解 → 技能执行”方面表现出良好工程可行性。

- **端到端具身大模型/VLA**：  
  - 在跨物体泛化和具备一定推理能力方面表现领先（如 RT‑2）；[24][41]  
  - 但在长程任务成功率和安全性方面存在显著不足，短期内更适合作为增强模块或在受控场景中部署。[6][28][42][43]

- **世界模型**：  
  - 在数据效率与物理一致性方面具有重要意义；[18][19][44][45]  
  - 目前主要在仿真‑现实迁移和策略优化中发挥作用，对终端产品的影响往往是间接的。

在实践中，多数公司采用混合架构：  
传统控制 + 分层大模型 + 模仿学习/强化学习 + 世界模型，而非单一路线。

## 6.2 不同公司在产品与商业化上的相对位置

以人形与具身机器人为主线：

- **先行商业化（物流/巡检）**：  
  - Boston Dynamics 的 Stretch 与 Spot 已实现商业销售和多地部署，是“具身智能真正赚钱”的典型案例。[72][73][74]  
  - 说明在相对结构化场景（仓储与巡检）中具身智能已能形成可持续业务。

- **工业与物流人形试点**：  
  - Agility Digit（与 Toyota 等合作）、Apptronik Apollo（与 Mercedes/Jabil 合作）体现出“人形进厂”的早期验证与小批量部署。[20][55][56][67][68][70]  
  - Figure AI 处于类似位置，但公开数据更多是融资与演示，而非具体部署量。[50][52][53]

- **消费与家庭场景探索**：  
  - 1X NEO/NEO Beta 面向家庭的试点计划；[23][63][64][65]  
  - 小米等公司推出的概念型人形（如 CyberOne）更多用于品牌与技术展示。[10][11]

- **规模化订单与量产**：  
  - Unitree 在四足与人形方向的出货量（五千台以上）显示其在量产方面领先，但销量数据存在不同口径，需要结合澄清公告谨慎解读。[78][79]  
  - UBTECH Walker S2 获得 8 亿人民币级订单并启动量产，标志“服务型人形机器人”已进入较成熟商务阶段。[83]

综合来看，2020–2026 年具身智能商业化的重心仍在物流／清洁／巡检等更可控场景，人形机器人在工业与服务场景中的规模应用处于起步阶段。

## 6.3 资本、技术与产品的耦合

资本在具身智能方向上的布局呈现出“软硬结合与平台化并行”的趋势：[27][50][51]

- 对垂直一体化公司（Figure、Agility、Apptronik、Unitree、UBTECH 等）的投资，主要押注其“本体+大模型+场景解决方案”的工程能力；  
- 对机器人大脑/世界模型平台公司的投资，旨在构建可复用、可横向扩展的决策与学习基础设施（Physical Intelligence、Skild AI 等）。  

同时，政策与标准化工作（尤其是在中国）为具身智能大规模应用提供了方向指引与安全边界。[3][6][12][13]

## 6.4 关键不确定性与中长期趋势

基于当前证据，中长期存在如下关键不确定性：

1. **端到端路线 vs 分层/世界模型路线**  
   - 一方面，端到端 VLA 在泛化能力与简化工程流程方面具有吸引力；  
   - 另一方面，世界模型与分层架构在安全性、可解释性和场景可控性上更现实。[6][18][19][30][31][47][48]  
   目前迹象表明，未来较长时间内两类路线将以“混合架构”共存。

2. **成本下降与量产时间表**  
   - 多份报告预期 2026 年会是人形机器人量产拐点，但当前出货量和收入规模仍有限。[4][7][8][27][85][86]  
   - 关键变量包括：本体成本、可靠性、维护成本及真实场景中的 ROI。

3. **场景泛化与安全效能**  
   - 现有系统在分布外场景和长程任务上的可靠性仍不足，尤其是在开放家庭环境中的人身安全与责任问题尚待解决。[6][28][42][43][44][45]

4. **人才密度与生态完善程度**  
   - “机器人+大模型+世界模型+控制”复合人才仍然稀缺，开源工具与标准接口尚不完备。[1][3][6][18][44][45][46]

## 6.5 给投资与产业决策的几点启示（基于证据的判断）

在现阶段，基于本报告所用证据，可以谨慎提出以下观察：

- 从 **技术路线** 看，短期更应关注“分层大模型 + 模块化控制 + 世界模型增强”的综合能力，而非单一端到端叙事；  
- 从 **场景选择** 看，工业制造（尤其是汽车与 3C）、仓储物流和巡检仍是具身智能商业化最可行的主战场；  
- 从 **公司选择** 看，应重点关注在以下方面同时有进展的企业：  
  - 有明确的场景闭环（真实付费客户与部署案例）；  
  - 在本体、算法与系统工程上具备深度掌控能力；  
  - 与“机器人大脑”公司或上游模型有清晰协同关系。  

同时，对高估端到端能力、过度依赖远期叙事而缺乏工程和场景闭环支撑的项目，应保持审慎。

---

## 参考文献

[1] A Comprehensive Survey on Embodied Intelligence: Advancements, Challenges, and Future Perspectives, CAAI Artificial Intelligence Research, 2024, https://www.sciopen.com/article/10.26599/AIR.2024.9150042  

[2] A review of embodied intelligence systems: a three-layer framework integrating multimodal perception, world modeling, and structured strategies, Frontiers in Robotics and AI, 2025, https://www.frontiersin.org/journals/robotics-and-ai/articles/10.3389/frobt.2025.1668910/full  

[3] 中国人工智能系列白皮书—具身智能（2026 版）, 2026, https://ceai.caai.cn/static/upload/file/20260412/1775977669687642.pdf  

[4] 2026年具身智能产业发展研究报告, 2026, https://pdf.dfcfw.com/pdf/H3_AP202602051819786211_1.pdf  

[5] 机器人正在“进化”——2026年中国机器人与具身智能市场十大趋势洞察, IDC, 2026, https://www.idc.com/resource-center/blog/%E6%9C%BA%E5%99%A8%E4%BA%BA%E6%AD%A3%E5%9C%A8%E8%BF%9B%E5%8C%96-2026%E5%B9%B4%E4%B8%AD%E5%9B%BD%E6%9C%BA%E5%99%A8%E4%BA%BA%E4%B8%8E%E5%85%B7%E8%BA%AB%E6%99%BA/  

[6] 具身智能发展报告, 中国信息通信研究院, 2026, http://www.caict.ac.cn/kxyj/qwfb/bps/202601/P020260130541978285206.pdf  

[7] 具身智能产业发展现状与趋势调研报告, 2025, https://file.jgvogel.cn/125/upload/resources/file/650706.pdf  

[8] 2026具身智能产业发展研究报告：量产拐点降临, CSDN, 2026, https://blog.csdn.net/weixin_42376192/article/details/158125305  

[9] Top 8 Humanoid Robot Companies to Watch in 2026, EVST, 2026, https://www.evsint.com/top-8-humanoid-robot-companies-2026  

[10] Top 12 Humanoid Robots of 2026, Humanoid Robotics Technology, 2026, https://humanoidroboticstechnology.com/articles/top-12-humanoid-robots-of-2026  

[11] 30+ Humanoid Robot Companies Ranked: Who’s Winning in 2026, Robozaps, 2026, https://blog.robozaps.com/b/humanoid-robot-companies  

[12] 市场持续扩张具身智能规模化应用提速, 福建省工信厅, 2026, https://gxt.fujian.gov.cn/zwgk/xw/hydt/xydt/202604/t20260402_7118522.htm  

[13] Unitree Can Build the Body, Can It Build the Mind?, Tech Buzz China Insider, 2025, https://techbuzzchina.substack.com/p/unitree-can-build-the-body-can-it  

[14] 具身智能或迎量产交付关键年, 新浪财经, 2026, https://finance.sina.cn/stock/jdts/2026-01-30/detail-inhkakfm3671271.d.html  

[15] Embodied Artificial Intelligence in Healthcare: A Systematic Review…, Healthcare, 2025, https://pmc.ncbi.nlm.nih.gov/articles/PMC12985249  

[16] 科技推动力：走进正在加速进化的具身智能机器人产业, 2025, https://www.youtube.com/watch?v=anvNxZKjNa8  

[17] Large Model Empowered Embodied AI: A Survey on Decision-Making and Embodied Learning, arXiv, 2025, https://arxiv.org/html/2508.10399v1  

[18] 大模型赋能的具身智能：自主决策和具身学习技术的全面最新综述, 龙腾亚太, 2026, https://www.longtengyatai.com/info/284  

[19] Embodied AI: From LLMs to World Models, IEEE Circuits and Systems Magazine, 2025, https://mn.cs.tsinghua.edu.cn/xinwang/PDF/papers/2025_Embodied%20AI%20from%20LLMs%20to%20World%20Models.pdf  

[20] Agility Robotics 官网, https://www.agilityrobotics.com  

[21] Humanoid Robot 'Digit' – Whole-Body Control Foundation Model, NVIDIA, https://www.nvidia.com/en-us/case-studies/agility-robotics-digit-humanoid-robot/  

[22] 1X World Model | From Video to Action, 1X, https://www.1x.tech/discover/world-model-self-learning  

[23] 1X Unveils NEO Beta, 1X, https://www.1x.tech/discover/announcement-1x-unveils-neo-beta-a-humanoid-robot-for-the-home  

[24] 具身智能即将为通用机器人补全最后一块拼图, AGIBOT, 2025, https://www.agibot.com/article/188/detail/7.html  

[25] This is Apptronik’s humanoid robot, Apollo, Apptronik, https://apptronik.com/news2  

[26] Humanoid Robot Comparison Tracker, New Market Pitch, 2026, https://newmarketpitch.com/blogs/news/humanoid-robot-comparison  

[27] Global Commercial Humanoid Robotics Market Research 2025‑2030, Yahoo Finance, 2025, https://uk.finance.yahoo.com/news/global-commercial-humanoid-robotics-market-113500094.html  

[28] 具身智能发展报告 – 技术路线章节, 2026  

[29] 大模型时代的具身智能, 哈工大报告, 2024, https://ssatt.bj.bcebos.com/2024/%E5%BC%A0%E4%BC%9F%E7%94%B7%EF%BC%88%E5%93%88%E5%B0%94%E6%BB%A8%E5%B7%A5%E4%B8%9A%E5%A4%A7%E5%AD%A6%EF%BC%89%EF%BC%9A%E5%85%B7%E8%BA%AB%E5%A4%A7%E6%A8%A1%E5%9E%8B%E5%85%B3%E9%94%AE%E6%8A%80%E6%9C%AF%E4%B8%8E%E5%BA%94%E7%94%A8.pdf  

[30] 具身智能核心技术解析：三大技术路线构建虚实交互新范式, Imagination, 2026, https://imgtec.eetrend.com/blog/2026/100599233.html  

[31] 大模型赋能的具身智能（技术综述全文）, 龙腾亚太, 2026  

[32] Embodied Artificial Intelligence in Healthcare…, Healthcare, 2025  

[33] Embodied AI | NEC Labs, https://www.nec-labs.com/research/media-analytics/projects/embodied-ai  

[34] 同上项目技术说明, NEC Labs, 2025  

[35] ChatGPT for Robotics 相关介绍（见 [24] 引用章节）  

[36] Vision-Language-Action Models: Concepts, Progress …, arXiv:2505.04769, 2025, https://arxiv.org/html/2505.04769v1  

[37] 大模型时代的具身智能 – 通用执行模型示意, 2024  

[38] 同上 – 具身执行大模型示意  

[39] 智元机器人 EI‑Brain 架构介绍, 见 [24]  

[40] RT‑1 相关描述, 见 [24]  

[41] RT‑2 相关描述, 见 [24]  

[42] 具身智能发展报告 – 端到端 VLA 评估章节, 2026  

[43] Gemini Robotics‑ER 任务成功率数据, 具身智能发展报告附录, 2026  

[44] World Model：从强化学习到具身智能的完整入门, 2024, https://liyang619.github.io/wm-tutorial/  

[45] World Model for Robot Learning: A Comprehensive Survey, arXiv:2605.00080, 2026, https://arxiv.org/html/2605.00080v1  

[46] Embodied AI Paper List, HCPLab-SYSU, 2025, https://github.com/HCPLab-SYSU/Embodied_AI_Paper_List  

[47] 随笔：2024的我们应该如何看待具身智能, Boyuan Space, 2024, https://www.boyuan.space/blogs/jushenzhineng.html  

[48] 同上 – 行为克隆与世界模型讨论  

[49] 1X | Home Robots, https://www.1x.tech/  

[50] The Year Of Humanoid Robots, Crunchbase News, 2024, https://news.crunchbase.com/robotics/ai-humanoid-robots-venture-funding-2024  

[51] Robotics Startups On The Rise In 2024, Crunchbase News, 2024, https://news.crunchbase.com/robotics/humanoid-startup-venture-ai-2024-figure  

[52] Figure AI 公司概览, EmbodyVC, https://embodyvc.com/companies/figure-ai  

[53] Figure AI – Wikipedia, https://en.wikipedia.org/wiki/Figure_AI  

[54] Humanoid Robot Comparison Tracker – Digit 能力表项, 见 [26]  

[55] Agility Robotics Announces Commercial Agreement with Toyota, 2024, https://www.agilityrobotics.com/content/agility-robotics-announces-commercial-agreement-with-toyota-motor-manufacturing-canada  

[56] Toyota Canada will Deploy Agility’s Digit, LinkedIn, 2024  

[57] Tesla’s Optimus Robot: Uses and Release Timeline, Built In, 2024, https://builtin.com/robotics/tesla-robot  

[58] Tesla Optimus Production Timeline, Optimusk Blog, 2024, https://optimusk.blog/blog/tesla-optimus-production-timeline  

[59] AI & Robotics | Tesla, https://www.tesla.com/AI  

[60] Tesla Optimus Gen 2 Review, Robozaps, 2025, https://blog.robozaps.com/b/tesla-optimus-gen-2-review  

[61] Tesla Optimus Pilot Production Line Video, Basenor, 2025  

[62] Optimus (robot) – Wikipedia, https://en.wikipedia.org/wiki/Optimus_(robot)  

[63] About – 1X, https://www.1x.tech/about  

[64] 1X unveils NEO Beta, The Robot Report, 2025, https://www.therobotreport.com/1x-unveils-neo-beta-as-it-prepares-to-deploy-into-home-pilots  

[65] 1X – Wikipedia, https://en.wikipedia.org/wiki/1X_Technologies  

[66] Apollo - Apptronik, https://apptronik.com/apollo  

[67] Apptronik and Mercedes‑Benz Enter Commercial Agreement, 2024, https://apptronik.com/news-collection/apptronik-and-mercedes-benz-enter-commercial-agreement  

[68] Apptronik and Jabil Collaborate to Scale Production of Apollo, Jabil, 2025, https://investors.jabil.com/news/news-details/2025/Apptronik-and-Jabil-Collaborate-to-Scale-Production-of-Apollo-Humanoid-Robots-and-Deploy-in-Manufacturing-Operations/default.aspx  

[69] Case study: Apptronik & TI, Texas Instruments, https://www.ti.com/about-ti/company/case-study/apptronik.html  

[70] Humanoid Robots Assist Assembly Lines, NASA Spinoff, https://spinoff.nasa.gov/Humanoid_Robots_Assist_Assembly_Lines  

[71] 同上  

[72] Boston Dynamics’ Stretch Robot Now Available for Commercial Purchase, 2023, https://bostondynamics.com/news/boston-dynamics-stretch-robot-now-available-for-commercial-purchase  

[73] Stretch and Spot: Increasing Operational Efficiency…, Robotics Tomorrow, 2024, https://www.roboticstomorrow.com/article/2024/11/stretch-and-spot-increasing-operational-efficiency-and-making-warehouse-work-safer/23525  

[74] Otto Group deploying Boston Dynamics’ robots in 20+ facilities, The Robot Report, 2024, https://www.therobotreport.com/otto-group-deploying-boston-dynamics-robots-in-20-facilities  

[75] Atlas Humanoid Robot | Boston Dynamics, https://bostondynamics.com/products/atlas  

[76] Unitree Robotics 官网, https://www.unitree.com  

[77] Official Open Source - Unitree Robotics, https://www.unitree.com/cn/opensource  

[78] Unitree Ranks No.1 Globally in Humanoid Robot Shipments, PR Newswire, 2025  

[79] Clarification Regarding Unitree's 2025 Sales Data, Unitree, 2025  

[80] 同 [13]  

[81] UBTECH 官网, https://ubtrobot.com/en/  

[82] UBTECH Walker X 产品页, https://www.ubtrobot.com/en/humanoid/products/walker-x  

[83] UBTECH Humanoid Robot Walker S2 Begins Mass Production…, Robotics Tomorrow, 2025, https://www.roboticstomorrow.com/story/2025/11/ubtech-humanoid-robot-walker-s2-begins-mass-production-and-delivery-with-orders-exceeding-800-million-yuan/25810  

[84] UBTECH Showcases its Latest Humanoid Robots at LEAP 2025, PR Newswire, 2025  

[85] Global Humanoid Robots Market Research 2026-2036, Yahoo Finance, 2026, https://uk.finance.yahoo.com/news/global-humanoid-robots-market-research-103800707.html  

[86] 同 [27]  

[87] 具身智能中强化学习如何降低数据量需求, 飞书文档, 2025, https://docs.feishu.cn/v/wiki/ZilLwDb9CiUV60kB5zocDbBgnYc/ah