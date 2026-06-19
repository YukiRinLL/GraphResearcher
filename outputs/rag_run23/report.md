# 全球具身智能（Embodied AI）技术路线与代表性玩家梳理（截至2026-06公开信息）

## 执行摘要

本报告聚焦“具身智能（Embodied AI）”这一连接网络空间与物理世界的技术方向。综合多篇最新综述，具身智能被视为通过“感知—认知—行为（Perception–Cognition–Behavior）闭环”在真实或高保真仿真环境中持续交互的智能体形态，核心目标包括具身感知、具身交互、具身智能体和仿真到现实迁移（sim-to-real）。多模态大模型（包括视觉语言模型、Vision-Language-Action 模型等）与世界模型被普遍认为是实现具身智能的重要基础架构。 [1][2]

从技术路线看，当前具身智能主要沿几条路径演进：一是以强化学习和模仿学习为核心的技能学习路线，结合大规模仿真和 sim-to-real 域自适应，在导航和操作任务上显著降低真实数据需求；二是“大模型赋能具身智能”路线，将 LLM/LVM/VLM/VLA 作为高层规划器与知识库，通过 Structured Language Planning、In-Context Learning 等方式实现跨任务迁移，并用 RLHF 对齐行为；三是世界模型驱动路线，通过学习环境动力学和任务结构，为规划和策略学习提供内部表征，并在机器人数据生成（Robotic Data Generation）中发挥作用；四是传统 modular / hierarchical 控制与深度学习结合的路线，通过分解探索、导航与操作等子任务，在复杂场景中支持长时程任务。 [2][3][4][5][6][7]

从产业和资本维度看，具身智能已形成以机器人为核心的高速增长子市场。商业研究机构预测，全球具身 AI 市场规模有望从 2025 年约 44.4 亿美元增长到 2030 年约 230.6 亿美元，复合年增长率约 39%，其中机器人相关应用是增长最快的子类，物流与供应链场景被认为是 2025–2030 年间增速最高的垂直行业。区域上，北美当前收入占比最高，亚太被视为增速最快地区；代表性厂商横跨 SoftBank Robotics、ABB、Toyota、Agility Robotics、Hanson Robotics 等传统工业与新兴机器人企业。需要注意，这类市场规模与结构预测基于机构内部模型，具体方法论未完全公开，数值存在不确定性。 [8]

在公司层面，全球具身智能玩家呈现出“大模型平台 + 机器人公司”的生态结构。一类是以 OpenAI 等为代表的大模型平台，其角色更偏向提供通用“语义与规划大脑”：一方面在 Dactyl 等项目中探索基于强化学习和大规模仿真的 dexterous manipulation 与 sim-to-real 技术路线；另一方面通过 GPT-4 等 API 向机器人公司开放能力，在多篇行业报道中被形容为机器人系统的“universal AI brain”。另一类是 Figure、Apptronik、Agility Robotics、1X、Tesla、Toyota/TRI、PAL Robotics 等人形或移动机器人公司，主打通用或特定场景的人形/移动机器人形态，在仓储物流、制造、零售和护理等场景进行试点或早期商业部署。 [9][10][11][12][13][14][15][16][17][18]

资本层面，具身智能尤其是人形机器人赛道在 2023–2025 年迎来显著升温。Figure AI 在 2024 年完成一笔约 6.75 亿美元、估值约 26 亿美元的融资，投资方包括 OpenAI、Microsoft、Nvidia、Intel 等，并与 OpenAI 签署合作协议共同开发面向 humanoid 机器人的下一代 AI 模型；后续投研机构的研究显示，Figure AI、Apptronik、Agility Robotics 的累计融资额和估值均已达到数亿美元乃至十亿美元级别。与此同时，行业分析指出专利布局和融资并不完全一致，例如 PatentVest 以 Figure 与 Sanctuary AI 为例，指出前者在专利数量上远少于后者，但融资额和估值更高。上述估值与融资规模多来自二级研究与行业报告，具体数字可能随时间更新，需结合一手披露进一步核实。 [19][20][14][21]

从成熟度看，学术论文和行业评论普遍认为当前人形机器人和通用具身智能仍处于“技术验证 + 早期试点”阶段，距离在大规模工业环境中广泛部署仍存在显著不确定性。以人形机器人为例，2021 年 Tesla AI Day 上的 Optimus 发布被视为引发新一轮竞赛的节点，但系统性评估指出，在感知、规划、能耗、执行器设计等方面仍有大量工程和安全挑战，对“未来两三年内广泛部署”的预期持审慎态度，并将当前热度与自动驾驶早期过度乐观的周期进行对比。 [22][23]

本报告在撰写时点为 2026 年 6 月，系统整理了 2018 年以来具身智能相关的论文、公司官网信息、投融资报道和市场研究。需要特别说明：一方面，部分公司（尤其是未上市初创企业）对技术细节、订单收入、估值与股权结构披露有限，报告中融资规模与估值多依赖新闻报道和投研机构估算，存在误差区间；另一方面，不同来源对同一公司的累计融资和估值存在差异，例如针对 Figure AI 的融资总额与估值，不同研究机构和专利分析报告的数字并不完全一致。本报告在相应章节将以“信息有限”“公开资料未完全披露”“不同来源存在差异”等方式提示不确定性，建议投资人将本报告视为基于截至 2026-06 公开信息的 best-effort 整理，而非法律或财务意义上的尽调结论。 [14][21]

## 一、具身智能的定义与产业边界

从学术综述角度看，具身智能（Embodied Intelligence / Embodied AI）通常被定义为：能够在物理世界中通过“感知—认知—行为（Perception–Cognition–Behavior, PCB）闭环”持续交互的智能体，它不仅处理视觉、语言等多模态信息，还需要在具体环境中采取动作并根据结果更新内部状态。多篇综述将具身智能的研究目标概括为具身感知（embodied perception）、具身交互（embodied interaction）、具身智能体（embodied agent）以及仿真到现实迁移（sim-to-real adaptation），并强调多模态大模型（Multi-modal Large Models, 包括 VLM/VLA 等）与世界模型（World Models）是支持具身智能体感知、推理与行动的重要技术架构。 [1][2]

具身智能任务在数据形态与训练范式上具有显著区别于传统计算机视觉或纯 NLP 的特征。香港中文大学（深圳）团队的具身 AI 数据综述指出，具身场景中的技能模型（skill models）通常采用强化学习（Reinforcement Learning, RL）和模仿学习（Imitation Learning, IL）进行训练；另一篇综述进一步强调，RL 和 IL 是具身技能学习的核心范式，需要大量机器人数据。相关工作还系统讨论了真实机器人数据与仿真数据在成本、可控性和分布覆盖等方面的权衡，指出在实践中会结合 human demonstration data、多模态 trajectories、visuomotor policy、RL 经验池等机制来提高数据效率和策略质量。 [2][4][24]

在算法层面，近期综述将“大模型赋能具身智能”视为一条新的主线，把大语言模型（LLM）、视觉大模型（LVM）、视觉语言模型（VLM）、多模态大模型以及 Vision-Language-Action（VLA）模型等统称为 large models，并专门讨论“Embodied Large Models”。这些大模型可以在具身系统中承担高层规划器、自然语言接口和世界知识库的角色，通过 Structured Language Planning、In-Context Learning（ICL）等机制实现零样本或小样本任务迁移，同时结合 RLHF 等手段对齐具身 agent 的行为偏好。 [3][25]

另一条并行技术主线是“世界模型（world models）驱动的具身智能”。相关预印本对具身世界模型给出了系统的技术分类法，从模型结构和应用领域两个维度梳理工作，指出具身世界模型在具身任务中的角色包括：学习环境动力学和任务结构，为 planning 和 policy learning 提供内部表征；作为强化学习、模仿学习等方法的环境代理；以及在“Robotic Data Generation”等场景中用于生成或扩展机器人训练数据。这些工作共同支撑了将世界模型视为具身智能基础设施的一种趋势。 [25][7]

从产业边界来看，具身智能通常被视为连接“网络空间（cyber space）”与“物理世界（physical world）”的技术体系，涵盖 embodied perception、embodied interaction、embodied agent 和 sim-to-real adaptation 等多个层次。其与传统工业机器人和自动驾驶的主要区别在于：一是任务空间更开放、长时程决策需求更强，需要在非结构化环境中完成多步骤任务；二是高度依赖多模态感知和大模型推理，而不是预先编程的刚性流程；三是仿真环境、世界模型和数据策略在整个闭环中扮演更加核心的基础设施角色。现有综述在产业场景上覆盖从室内导航、家用与服务机器人、仓储物流到人形机器人等，但对具体商业模式与价值链分工往往只作概括描述，尚难形成统一、细颗粒度的产业边界划分。 [1][2][3]

## 参考文献

[1] Paper List and Resource Repository for Embodied AI https://github.com/HCPLab-SYSU/Embodied_AI_Paper_List

[2] A Comprehensive Survey on Embodied Intelligence: Advancements, Challenges, and Future Perspectives https://www.sciopen.com/article/10.26599/AIR.2024.9150042

[3] Large Model Empowered Embodied AI: A Survey on Decision-Making and Embodied Learning https://arxiv.org/html/2508.10399v1

[4] A Survey of Embodied Artificial Intelligence Data ... https://airs.cuhk.edu.cn/sites/default/files/2025-06/Survey_Arxiv.pdf

[5] Bi-directional Domain Adaptation for Sim2Real Transfer of Embodied Navigation Agents https://ai.meta.com/research/publications/bi-directional-domain-adaptation-for-sim2real-transfer-of-embodied-navigation-agents

[6] Embodied AI https://www.nec-labs.com/research/media-analytics/projects/embodied-ai

[7] A Survey of Embodied World Models https://www.preprints.org/manuscript/202604.0928

[8] Embodied AI Market Report 2025 - 2030 https://www.marketsandmarkets.com/Market-Reports/embodied-ai-market-83867232.html

[9] Learning dexterity https://openai.com/index/learning-dexterity/

[10] Learning Dexterous In-Hand Manipulation https://arxiv.org/abs/1808.00177

[11] Learning dexterous in-hand manipulation https://www.researchgate.net/publication/337345997_Learning_dexterous_in-hand_manipulation

[12] RBR50 Spotlight: OpenAI enabling embodied AI to flourish https://www.therobotreport.com/rbr50-spotlight-openai-enabling-embodied-ai-to-flourish/

[13] 30+ Humanoid Robot Companies Ranked: Who's Winning in 2026 https://blog.robozaps.com/b/humanoid-robot-companies

[14] Figure vs Apptronik vs Agility Robotics https://sacra.com/research/figure-vs-apptronik-vs-agility-robotics

[15] Boston Dynamics and Toyota Research Institute Announce Partnership to Advance Robotics Research http://www.tri.global/news/boston-dynamics-and-toyota-research-institute-announce-partnership-advance-robotics-research

[16] Robotics at Toyota | Toyota Europe https://www.toyota-europe.com/innovation/mobility-solutions/robotics

[17] Robotics | Toyota Research Institute http://www.tri.global/our-work/robotics

[18] Europe’s Humanoid Robotics Moment (LinkedIn post) https://www.linkedin.com/posts/sylviastocker_europes-humanoid-robotics-moment-when-activity-7402690081700081664-tPiI

[19] Figure: AI Robotics Company Raises $675 Million At $2.6 Billion Valuation And Deal Signed With OpenAI https://pulse2.com/figure-ai-robotics-company-raises-675-million-at-2-6-billion-valuation-and-deal-signed-with-openai/

[20] Humanoid robot-maker partners with OpenAI, gets backing from tech giants https://www.seattletimes.com/business/humanoid-robot-maker-figure-partners-with-openai-and-gets-backing-from-jeff-bezos-and-tech-giants/

[21] Humanoid Robots: The Disconnect Between IP Strength And VC Funding Of US And European Humanoid Robot Startups https://www.patentvest.com/patentvest-pulse/humanoid-robots-the-disconnect-between-ip-strength-and-vc-funding-of-us-and-european-humanoid-robot-startups

[22] AI & Robotics https://www.tesla.com/AI

[23] Humanoid Robots at work: where are we ? https://arxiv.org/html/2404.04249v1

[24] What Data Imperative for Action Learning in Embodied AI? (2) https://yuhuang-63908.medium.com/what-data-imperative-for-action-learning-in-embodied-ai-2-882c4ade2e7d

[25] Embodied AI: From LLMs to World Models [Feature] https://mn.cs.tsinghua.edu.cn/xinwang/PDF/papers/2025_Embodied%20AI%20from%20LLMs%20to%20World%20Models.pdf
