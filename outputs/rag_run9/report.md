# 引言：研究范围与关键概念

本报告基于 2020–2025 年公开资料，系统梳理全球具身智能（Embodied AI）技术路线，并围绕代表性公司的技术路径、产品进度、商业化模式、融资与团队特征进行分析。在必要处延伸到 2026 年早期进展。所有事实性信息均来自公开报告、学术综述、企业披露和政策文件等，引用处以编号标注。

Encord 等认为，具身智能指具有物理形态，并能通过多模态传感器感知环境、在物理世界执行动作的 AI 系统，包括各类机器人和自动驾驶车辆[1]。关键技术组件包括多模态感知、机器人控制、强化学习（RL）、模仿学习（IL）、世界模型以及大语言/视觉语言模型（LLM/VLM）等[1]。

多份学术和产业综述显示，2020–2025 年间，具身智能技术从传统的“感知-规划-控制”模块化架构，逐步演进为“世界模型+大模型+控制”整合框架[2][3][4][5][6]。PNP Robotics、工业柔性制造综述等文献强调，多模态感知（视觉、语言、力觉）与运动控制、规划的深度融合是重要趋势，而不仅是简单串联[2][3]。

中国信通院 2024 年报告将具身智能技术路线概括为四类：大模型+机器人、模仿学习/强化学习路线、端到端视频到控制路线以及经典控制+AI 混合路线，并指出行业整体仍处于“技术验证+小规模试点”阶段，人形机器人尚未进入大规模通用部署[4][7]。学术界对 RL/IL 与世界模型、大模型结合的演进，也在多个白皮书和综述中得到系统讨论[5][6][8][9]。

在政策层面，中国和美国已经将具身智能/智能机器人纳入国家或拟议的战略框架，中国更是将“physical AI / embodied AI”列为与量子技术、生物制造等并列的关键技术方向之一[10][11][12][13]。日本、欧洲等地区也通过科技战略报告和产业计划推动具身智能与机器人融合[14][15][16]。

本报告的分析框架如下：

- 第一章：从能力栈出发，梳理全球具身智能的五大技术路线，并讨论区域政策差异。
- 第二章：聚焦 Tesla Optimus、Figure、1X、Agility 四家公司，补充以 Boston Dynamics、优必选、傅利叶、云深处等为对比。
- 第三章：按家用、工业、仓储、服务机器人四类，讨论产品落地和应用场景。
- 第四章：总结商业化模式、收入结构与主要障碍。
- 第五章：梳理代表性公司的融资格局和团队特征。
- 结语：对 2020–2025 阶段性进展与未来 3–5 年进行谨慎研判，并说明数据局限。

需要特别说明的是，目前公开数据在精细收入拆分、合同条款、详细技术架构和完整融资表等方面仍然有限，报告中对这些部分多以定性描述和案例点状信息为主，并在相关段落明确标注“数据有限”或“不宜过度外推”。

---

## 第一章 全球具身智能技术路线总览

### 1.1 技术定义与能力栈

Encord 将 Embodied AI 定义为“带有物理形态（机器人、自驾车等）、能够感知并作用于世界的 AI 系统”，并将多模态感知、机器人控制、强化学习、模仿学习、世界模型以及 LLM/VLM 视为核心组成[1]。来自中山大学 HCPLab 的 Embodied AI 资源库以任务类型（家务/室内任务、导航、具身对话、交互式代理等）和平台（Habitat、AI2-THOR、iGibson 等）为索引，系统整理了 2019–2025 年的大量顶会论文，区分端到端与模块化方法[17][18]。

多个技术指南与白皮书从“能力栈”角度描述具身智能系统的层级结构：

- GitHub“具身智能技术指南”将栈划分为：
  - 底层：工程工具、几何、标定、控制；
  - 中层：视觉与多模态表征、SLAM、物体识别；
  - 上层：任务规划、强化学习、模仿学习，以及 LLM/VLM 驱动决策[6][19]。
- 张伟男的演讲从控制、几何与标定，到感知、表征、决策和任务/交互构建了一条自下而上的算法能力栈，并指出在端到端执行模型性能尚不达标前，抓取等精细任务仍高度依赖高精度感知与经典控制[20][21]。
- “基于大模型的具身智能系统综述”将大模型在系统中的角色划分为需求级、任务级、规划级和动作级，从自然语言需求理解到任务分解、规划生成直至低层控制[22][23]。
- 知乎综述《大模型赋能的具身人工智能：决策与具身学习》则将决策方式分为“分层决策范式”和“端到端决策范式”，认为工业项目中更常见的是前者：大模型负责任务规划和语言到任务映射，低层由传统控制或强化学习执行[24][25]。

工业领域的综述强调，在柔性制造场景中，具身智能方法主要分为三类：基于学习的控制（RL/IL）、基于模型的规划（任务与运动规划、生产调度）以及利用 VLM/LLM 进行任务理解与高层策略决策[3][26]。PNP Robotics 的综述指出，多模态感知（视觉、语言、力觉）与运动控制和规划的紧耦合，是连接网络空间与物理世界的关键[2][27]。

综合这些文献，可将具身智能能力栈概括为：

- 感知与表征：多摄像头纯视觉、RGB-D、力/触觉、多模态表征；
- 世界建模：物理模拟器、内部世界模型，用于预测未来状态和规划；
- 决策与策略学习：RL、IL、世界模型强化学习、VLA 模型；
- 低层控制与执行：全身控制、平衡控制、轨迹规划、伺服控制；
- 人机交互与任务规划：LLM/VLM 支撑的自然语言指令理解、任务分解与高层规划。

### 1.2 五大主流技术路线

根据中国信通院报告、国内外白皮书以及大模型具身综述，可将 2020–2025 年具身智能的主流技术路线归纳为五类[4][7][3][5][6][22][24][28]。

#### （1）大模型+机器人路线

中国信通院报告将“大模型+机器人”列为具身智能的核心技术路线之一，指通过 LLM/VLM/VLA 提供高层决策、任务规划与多模态交互，而低层仍由经典控制或学习控制承担[4][7]。  

“基于大模型的具身智能系统综述”提出，大模型可以在需求级（理解自然语言需求）、任务级（任务分解）、规划级（生成行动序列）和动作级（输出动作命令）扮演不同角色；在现实工业系统中，分层决策+大模型辅助仍是主流，端到端大模型控制多停留在实验系统[22][23]。知乎综述也指出，在工业实践中更常见的是“大模型负责任务规划，低层使用传统控制或 RL”的模式[24][25]。

典型代表包括：

- Figure 的 Helix VLA 模型，面向通用人形机器人，声称可以让机器人几乎抓取任意小型家用物体，包括大量未见过的对象[29][30]。
- Open X-Embodiment 项目的 RT-2 视觉-语言-动作大模型，通过多机器人多任务数据训练，旨在构建通用机器人控制模型[31][32]。
- 1X 的 Redwood AI，将其描述为基于真实机器人数据训练的“generalist AI model”，用于 NEO 家用机器人的任务学习与执行[33][34]。
- 中国大厂布局，如阿里通义千问团队组建“机器人和具身智能小组”，从原先专注多模态大模型转向“基础智能体+具身”方向[35][36]。

这一路线的共同特点是：大模型承担高层理解与决策，重视多模态输入（视觉+语言），在安全要求较高的工业与服务场景中仍采用分层结构，避免将低层控制完全交给大模型。

#### （2）强化学习/模仿学习路线（RL/IL）

中国信通院和中国人工智能学会白皮书都强调 RL/IL 在具身智能中的核心地位，同时指出其局限性和演进方向[4][5][8][9]。2026 版具身智能白皮书以 Stanford HumanPlus 项目为例，强调在模拟环境中用 RL 训练技能，同时在现实环境中进行模仿学习，实现具身技能的自主学习[8][9]。

2025 年具身智能行业研究报告指出，传统 IL/RL 在任务迁移时表现不稳定，面临任务变体时常需要重新设计奖励或策略，感知-认知-行动之间存在割裂，因此提出将 LLM/VLM 与机器人结合，以提高泛化能力[28][37]。

南京大学团队关于“从物理模拟器和世界模型中学习具身智能”的综述区分了物理模拟器与世界模型：前者提供安全、可控的训练环境，后者通过内部预测未来状态补充模拟不足；通过在仿真中用 RL 训练、结合 IL 可以减小 sim-to-real 差距并提高样本效率[38][39][40][41]。

这一路线在工业柔性制造综述中被归为“基于学习的控制”，与基于模型的规划和大模型辅助决策形成互补[3][26]。

#### （3）端到端视觉到控制路线

端到端具身智能指通过统一神经网络从视觉/视频直接映射到控制信号。中国信通院将“端到端视频到控制”视作一条独立技术路线[4][7]。

典型案例：

- Tesla Optimus：财联社报道，Optimus 采用从视频输入到控制信号输出的“完全端到端”神经网络训练方案，并依托 Dojo 等专用算力平台进行大规模训练[42][43]；知乎长文进一步描述其通过 VR+动作捕捉采集人类演示、多模态数据训练端到端网络，将人类技能迁移到机器人，实现模仿学习与端到端控制结合[44][45]。
- Wayve 将其端到端自动驾驶系统视作具身智能的一种，直接将摄像头和其他传感器输入映射到驾驶控制，目标是在多城市、多条件下实现通用驾驶能力[46][47]。
- 傅利叶 GR-1 人形机器人在纯视觉端到端感知上采用 BEV+Transformer+OCC，使用 6 个 RGB 摄像头实现 360 度视角，将感知结果用于导航、避障和任务执行，明显借鉴自动驾驶纯视觉端到端方案[48][49][50][51]。

然而，张伟男等指出，端到端执行模型在抓取等精细任务上的性能尚不足以取代依赖精确感知和经典控制的方案，因此短期内大模型多承担高层任务理解和交互角色[20][21]。知乎与大模型综述也指出，端到端大模型控制多停留在实验验证阶段[22][23][24][25]。

#### （4）经典控制+AI 混合路线

中国信通院报告将“经典控制+AI 混合”视为重要路线之一，即在保持经典控制的稳定性与安全性的前提下，引入 AI 在感知、规划或调度层增强能力[4][7]。  

工业柔性制造综述将“基于模型的任务与运动规划”与“基于学习的控制”和“大模型辅助决策与感知”并列，强调在复杂工艺流程、生产调度和人机协作中，传统控制与 AI 的混合是现实可行路径[3][26]。

张伟男演讲中展示的能力栈也体现这一思路：底层仍依赖控制与几何标定等工程技术，而大模型主要嵌入在任务与交互层[20][21]。  

在业界，人形机器人如 Boston Dynamics Atlas 强调高性能运动控制与感知安全系统，官方页面并未突出大模型或端到端控制，而是以自研控制栈和闭源商业模式为主[52][53]。优必选则自称具备人形机器人全栈能力，包括运动规划与控制、高性能伺服驱动器以及“仿人大脑”等 AI 技术[54][55]，体现经典控制+AI 的混合路径。

#### （5）世界模型+仿真驱动的闭环 RL 路线

南京大学综述及其评述文章强调，将物理模拟器和世界模型结合，通过在仿真中进行 RL 训练并配合 IL，可以缓解 sim-to-real 差距，提高样本效率，降低真实环境试验的风险和成本[38][39][40][41]。世界模型为机器人提供对未来场景的预测能力，从而减少在真实环境中的试错需求[40][41]。

这一路线在 Open X-Embodiment 的 RT-X 体系中也有所体现：RT-1 和 RT-2 通过多机器人、多任务的“世界”数据训练，旨在构建跨平台的通用控制模型[31][32][56][57]。DeepMind 博文提到，RT-1-X 通过整合不同机器人平台的数据混合训练，相比原 state-of-the-art 在任务成功率上约提升 50%，体现“跨机器人类型的世界经验”带来的泛化能力提升[56][57]。

总体看，世界模型与仿真驱动的路线多与 RL/IL 和大模型结合，形成闭环：模拟环境 + 世界模型 → RL/IL 训练策略 → sim-to-real 迁移到实体机器人。该路线在工业场景的安全性与成本约束下具有明显优势。

### 1.3 区域差异与国家政策/战略（北美、欧洲、日本、韩国、中国）

#### 中国：具身智能上升为国家战略

Carnegie Endowment 报告指出，中国已经将具身智能（smart robots）作为国家 AI 战略的核心方向之一，出台被称为“首个系统性具身智能路线图”的政策文件，推动服务机器人、工业机器人和人形平台等领域出现国家级“冠军企业”[58][59]。报告同时提到 Zeekr 工厂部署由优必选（UBTech）人形机器人组成的团队，这些机器人由基于 DeepSeek R1 的多模态推理模型驱动，执行搬运、装配和质检任务，并具备自主换电能力，实现 24 小时运行[60][61][62][63]。

MERICS 报告和 IFR 新闻稿进一步佐证：中国拥有全球最大工业机器人安装量，并在国家规划和产业政策中积极探索具身智能和人形机器人的应用，将 AI 驱动机器人视为国家发展蓝图的核心[64][65][66][67]。Six Degrees of Robotics 的专栏文章指出，一项新的中国规划将 physical AI/embodied AI 与量子技术、生物制造、氢能与聚变能、脑机接口等并列列入关键技术清单[10][11]。

国内研究报告估计，2023 年中国具身智能市场规模约 3647 亿元人民币，并认为大模型与传动控制的结合是下一阶段发展的核心驱动力[68][69]。这表明中国在政策、市场和产业布局上对具身智能给予高度优先级。

#### 美国：国家机器人战略与安全立法

美国智库和行业组织密集发布政策文件，呼吁制定国家机器人和具身智能战略。SCSP 的《Memos to the National Robotics Strategy》提出三大目标之一是“加速机器人和具身智能在美国各行业的采用”，并建议白宫牵头制定国家级机器人商业化战略、简化监管许可，重点在制造、实验室自动化、物流、农业和能源等领域部署机器人[70][71][72][73]。文件指出，美国在机器人软件和 AI 上有优势，但在机器人硬件商业化和规模应用上存在短板，而中国 2023 年工业机器人采用量已超过其他国家总和，并计划在 2027 年在人形机器人领域领先[72][73]。

A3 和 AUVSI 等行业组织的文件强调，美国在机器人这一 AI 的物理体现方面落后于其他国家，如果在机器人领域缺乏领导力，将可能在机器人和 AI 竞赛中同时失利[74][75][76][77]。他们呼吁设立中央机器人办公室和国家机器人战略委员会，通过税收激励与统一监管框架，推动 physical AI 的广泛部署[74][75][76][77]。

在安全与供应链角度，美国国会的 S.3275《Humanoid ROBOT Act of 2025》提议禁止联邦行政机构采购由“关注国家”相关实体开发的人形机器人，并限制联邦承包商在政府合同中使用此类机器人，要求国防部长评估来自这些国家的人形机器人对美国国家安全的威胁[78][79][80][81]。这反映出具身智能在中美技术竞争和安全政策中的重要性。

Hudson Institute 的报告则从“如何在具身智能前沿战胜中国”的角度，强调国家战略协调、供应链布局和国际标准制定的重要性[82][83]。

#### 日本与欧洲：以产业竞争力为导向的科技规划

日本 JST/CRDS 报告《Integration of Embodied AI and Robotics》将发展能够适应现实世界环境的具身智能与机器人技术作为提升日本国际竞争力的目标之一，强调通过融合传感、控制、学习和具身认知，发展在复杂环境中自适应的机器人系统，并与国家重点研发项目和产业协同、标准和社会接受度议题相联系[14][15][16][84]。

欧洲方面，Dimension Market Research 预测欧洲具身智能市场规模将在 2025 年约 7.21 亿美元、2034 年增长至约 87.56 亿美元[85][86]。Gerard de Valence 博客指出，中国“智能制造 2025”、日本机器人计划、德国“工业 4.0”和美国创新政策等国家战略都明确支持机器人产业发展[87][88][89]，但在具身智能/physical AI 专门政策层面，欧洲公开资料较为碎片化，更多通过工业自动化和 AI 战略间接推动。

#### 韩国及其他区域：数据有限

在本次图谱中，关于韩国与其他地区的具身智能专门政策和技术路线资料较为有限，主要是通过国际机器人联合会等机构的全球统计间接体现，缺乏系统性政策文件的细节，难以给出同等深度的比较。对于韩国、日本部分商业实践、创业公司和投资数据，本报告因缺乏可靠证据而不做具体评述。

---

## 第二章 代表性公司的技术路径与产品进度

本章重点分析 Tesla Optimus、Figure、1X、Agility 四家公司的技术架构、产品形态和 2020–2025 进展，并以 Boston Dynamics、优必选、傅利叶、云深处等为对照。由于各公司信息披露程度不同，本节有些方面（如具体控制架构、完整时间线和融资细节）数据有限，以下描述仅基于现有证据。

### 2.1 Tesla Optimus：纯视觉端到端与模仿学习结合

Tesla 官方将 Optimus 定位为“通用双足人形机器人”，目标是在共享 Tesla 纯视觉和神经网络控制技术栈的基础上，执行危险、重复或枯燥任务[90][91][92][93]。其 AI & Robotics 页面强调基于摄像头的纯视觉方案和大规模神经网络控制，车辆与未来机器人共用技术基础[90][91][92][93]。

财联社报道称，Optimus 采用从视频输入到控制信号输出的“完全端到端”神经网络训练方案，并依托 Dojo 等专用算力平台进行大规模训练[42][43]。知乎长文进一步指出，工程人员通过 VR 和动作捕捉设备演示任务，Optimus 采集多模态动作捕捉数据训练端到端神经网络，将人类技能迁移到机器人，实现模仿学习与端到端控制结合[44][45]。

个人博客基于 Tesla 平衡控制专利（WO2024/073088A1）分析，Optimus 采用利用视觉和神经网络实现全身平衡控制的架构，通过协调多个关节与躯干实现实时平衡[94][95]。这与 Tesla 在自动驾驶中基于纯视觉和神经网络控制的路线形成统一技术体系[90][91][92][93][94][95]。

关于 2020–2025 具体生产规模和部署场景，TS2.tech 等媒体报道到 2025 年中 Optimus Gen 3 已制造约千台（该信息存在于图谱后续部分，属于媒体报道，未在此段落中展开）。整体而言，Optimus 技术路径可归入“纯视觉端到端+IL”的路线，具有较强的自动驾驶技术迁移色彩。

### 2.2 Figure：通用人形 + VLA 模型 Helix

Figure AI 官网将公司定义为“致力于在多行业场景部署通用人形机器人的 AI 机器人公司”，称自己为“first-of-its-kind AI robotics company bringing a general purpose humanoid to life”，目标是在多个行业场景部署通用人形机器人，由先进 AI 模型提供智能[96][97]。Robots Guide 将 Figure 01 描述为等身双足人形，定位为通用机器人劳动者，可在工厂、仓储等人类环境中与人协作执行通用任务[98][99]。

Figure 发布的新闻稿介绍 Helix，这是专为通用人形机器人设计的 Vision-Language-Action 模型。公司声称，借助 Helix，其机器人几乎可以拾取任何小型家用物体，包括成千上万此前未见过的对象[29][30]。这表明 Figure 的技术路线属于“大模型+机器人”中的 VLA 路线，强调多模态数据驱动的通用操作能力。

商业化方面，Business Insider 报道，Figure 通过 24 小时直播展示其人形机器人在分拣包裹等仓储物流场景的应用，并与 JCPenney 等零售集团（包括其母集团 Catalyst Brands）签署商业协议，在仓储与物流场景以机器人即服务（RaaS）方式部署人形机器人[100][101][102]。该报道还提到，Figure 最新估值约 390 亿美元[103]，而华尔街日报此前报道其在 2025 年寻求以约 395 亿美元估值融资 15 亿美元[104][105]。图谱中将这两者间的差异标注为“轻微估值差异的冲突”，可能反映不同时间点或轮次的估值口径[106]。

需要强调的是，目前 Figure 官方未公开具体 RaaS 定价、客户合同条款或收入结构，现有信息主要来自媒体报道和平台宣传，详细商业模式仍不透明[107][108]。

### 2.3 1X Robotics：家用人形 NEO 与 Redwood AI

1X 官方主页将公司定位为“基于帕洛阿尔托的一家 AI 与机器人公司”，致力于打造安全的人形机器人，帮助用户处理家务并提供个性化辅助[109][110]。NEO 产品页说明，NEO 使用 Redwood AI——1X 的通用 AI 模型，用于学习和重复任务，并会随时间增强能力[33][34]。Redwood AI 被描述为基于真实机器人数据训练的“generalist AI model”，体现大模型驱动家用人形机器人的路线[33][34]。

在商业模式上，1X 的 NEO 提供双重定价：官网 Order NEO 页面显示，一种是每月 499 美元的订阅模式（Standard，月度订阅，包含 Starter Productivity Package 和标准配送），另一种是约 20,000 美元的一次性 Early Access 购买选项[111][112][113]。Mashable 和 Fortune 的报道进一步说明，订阅方案通常要求至少 6 个月承诺期，用户可以在不再需要时归还机器人，这被描述为一种“租赁+订阅”的使用权模式，而非完全拥有硬件[114][115][116][117][118]。  

从技术到商业，这表明 1X 的路线是：家用人形机器人 + 通用 AI 模型 + 双轨定价（CapEx 购买 + OpEx 订阅）。

融资格局方面，Tech Funding News 报道，OpenAI Startup Fund 在 2023 年领投了 1X 的一轮融资，金额约 2350 万美元[119][120][121]，并指出 1X 在加州海沃德建设了一个“首个垂直一体化 humanoid 工厂”[120][121]。The Robot Report 的 2026 年新闻汇总提到，到 2026 年 5 月，1X 已在海沃德工厂启动 NEO 人形机器人的生产[122][123]。这些信息表明，1X 已从技术原型进入早期量产阶段。

### 2.4 Agility Robotics：Digit 与 RaaS + 仿真基础模型

Agility Robotics 官网将 Digit 描述为“首个进入生产部署的人形机器人”，与云平台 Agility Arc 一起，为设施地面带来先进自动化[124][125]。Digit 主要面向仓储和物流等以人为本的环境，Arc 用于部署和管理 Digit 车队[124][126]。

在控制技术上，NVIDIA 官方案例指出，Agility 使用 NVIDIA Isaac Sim 和 Isaac Lab 以及 GPU 资源，为 Digit 构建“全身控制基础模型（whole-body control foundation model）”，以提升感知、运动和安全特性。这表明 Digit 的控制栈包含以仿真为核心的基础模型，属于“世界模型+仿真+RL/控制”的路线。

商业化方面，GXO Logistics 与 Agility 在 2024 年签署多年的 RaaS 协议，在美国乔治亚州 Spanx 仓库部署 Digit。Agility 官方新闻稿称这是“行业首个正式商业部署的人形机器人项目，也是首个人形机器人 RaaS 部署”。Digit 在仓库中从协作机器人（如 6 River Systems 的 Chuck）接过周转箱并放到输送线，这一流程由 Agility Arc 云平台编排。

The Robot Report 的第三方报道确认，GXO 在 Spanx 仓库以 RaaS 模式部署一小批 Digit，并按 RaaS 模式付费，但双方未披露具体价格、部署数量或合同条款。Agility 的博客将这次部署描述为历史性的“首次人形机器人正式上班”，强调 Digit 在多年的协议下成为 GXO 日常运营的一部分。

此外，Amazon 官方新闻稿表明，Amazon 在履约中心引入与 Agility 合作的 Digit 机器人，与 Sequoia 系统一起处理托盘和容器等任务，以提升安全与效率。这说明 Digit 已在多家头部物流/电商企业场景中进行试点或早期部署。

### 2.5 其他代表性公司的技术路径

#### Boston Dynamics：高机动性人形与控制栈

Boston Dynamics Atlas 被描述为高机动性双足人形机器人，设计目标是在与人类相同的工作站和设备环境中运行，依赖鲁棒感知和智能安全系统[52][53]。官方未公开大模型或端到端控制细节，更接近“经典控制+AI 混合”的闭源高端平台。

#### 优必选（UBTech）：全栈人形控制

优必选公司介绍称，其为“全球极少数具备人形机器人全栈式技术能力的公司之一”，能力覆盖机器人运动规划与控制、高性能伺服驱动器以及仿人大脑等人工智能技术[54][55]。Carnegie 报告进一步显示，优必选的人形机器人团队在 Zeekr 工厂执行搬运、装配和质检任务，使用基于 DeepSeek R1 的多模态推理模型，并具备自主换电能力[60][61][62][63]。这体现了“自研控制+大模型”的混合路线及在中国工业场景的规模化试验。

#### 傅利叶智能：纯视觉 BEV+Transformer 感知

傅利叶智能 GR-1 技术文章强调，其在人形机器人上率先部署纯视觉方案，融合 BEV、Transformer 和 OCC 技术，使用 6 个 RGB 摄像头实现 360 度视角，全局环境重建与语义理解，并将感知结果用于导航、避障和任务执行[48][49][50][51]。这是端到端纯视觉感知应用在中国人形机器人的典型案例。

#### 云深处科技：电力巡检四足机器人

云深处科技官网称自身为“具身智能技术创新与行业应用引领者”，是全球首家围绕电力巡检应用的智能四足机器人企业，并在中国率先实现四足机器人全自主巡检。其路线以四足形态为主，聚焦电力巡检等复杂环境中的感知、导航与任务执行，代表四足具身智能在行业落地上的路径。

#### Unitree 等：多形态平台与收入结构

Hello China Tech 和 TechFlow Post 基于 Unitree IPO 招股书分析指出，Unitree 当前与人形机器人相关的收入主要来自科研、教育和开发市场，而非大规模工业部署，主要营收仍来自用于安防和巡检的四足机器人产品线，软件和服务收入占比较低。这说明人形业务在部分公司中仍处于早期探索阶段。

---

## 第三章 产品落地与应用场景

本章按家用机器人、工业机器人、仓储机器人、服务机器人四类梳理 2020–2025 年的成熟度与典型案例。整体上，信通院报告认为，人形机器人和通用具身系统整体仍处于技术验证和小规模试点阶段，尚未进入大规模通用部署[4][7]。

### 3.1 家用机器人与人形/非人形差异

1X 的 NEO 是目前公开信息中较为典型的家用人形机器人案例。NEO 以家务和个性化辅助为目标，采用 Redwood AI 作为通用模型[33][34][109][110]，并通过 499 美元/月订阅或 2 万美元一次性购买的模式对消费者开放预订[111][112][114][115][117][118]。媒体报道提到 NEO 续航约 4 小时，面向家庭家务场景[117]。  

这类家用人形机器人与传统家用机器人（扫地机器人、单功能清洁机器人等）相比，主要差异在于：  
- 形态上采用双足或双足+轮式结构，能在以人为设计的环境中操作多种器具；  
- 控制上依赖通用大模型和多模态感知，支持任务学习与复用；  
- 商业模式上更倾向订阅与租赁组合，而非一次性销售。

由于现有证据中缺乏家庭用户规模、退订率、故障率等详细数据，对其成熟度的评价只能定性判断为“早期量产+商业试点阶段”。

### 3.2 工业机器人：柔性制造与人形平台

柔性制造领域的具身智能综述指出关键挑战包括受限感知下的鲁棒操作、复杂工艺流程规划和人机协作安全等[3][26]。在这一领域，大多数现有部署仍以传统工业机械臂和移动平台为主，具身智能更多体现在：

- 基于学习的控制（RL/IL）和大模型辅助决策提升柔性与自适应性[3][26]；
- 通过仿真和世界模型降低现实试验风险[38][39][40][41]；
- 在某些工厂试点引入人形平台，如 Zeekr 工厂部署由优必选人形机器人组成的团队执行搬运、装配和质检任务[60][61][62][63]。

Scientific Reports 关于建筑行业人形机器人应用的综述指出，建筑工地高度复杂、非结构化且变化快速，安全标准严格、经济性和 ROI 不确定，人机协同和技能抽象困难，导致许多人形机器人建筑应用项目在试点后被延期、缩减或转向更专用的施工机器人形态，难以实现大规模商业落地。这反映出在人形具身智能向重工业与建筑推广中的显著障碍。

### 3.3 仓储与物流机器人：人形 Digit 与非人形 AMR

仓储与物流是当前具身智能最活跃的应用场景之一。  

Agility 的 Digit 在 GXO Spanx 仓库的部署被多方报道为“首个人形机器人正式商业部署”和“首个人形 RaaS 协议”。Digit 在该场景中与 6 River Systems 的 Chuck AMR 协同工作：Chuck 将周转箱运至 Digit 工作站，由 Digit 将其放置到输送线，这一流程由 Agility Arc 云平台编排。GXO 与 Agility 的多年份 RaaS 协议强调 Digit 在日常运营中的长期角色。

Amazon 官方新闻稿显示，Amazon 在履约中心引入与 Agility 合作的 Digit 机器人，与 Sequoia 系统一起处理托盘和容器，提升安全与效率。这些案例表明，人形 Digit 与现有 AMR/ASRS 系统形成“人形+非人形”的混合自动化方案。

在成本与商业模式上，Monetizely 基于 Digit 等案例估计，人形仓储机器人当前运营成本约为每小时 10–12 美元，预计规模化后可降至 2–3 美元/小时；RaaS 模式下通常按预期运行小时或按周打包小时数计费，将客户支出转为运营费用。市场价格指南则指出，工业和物流类人形机器人在 RaaS 模式下的月费区间通常为 2,000–15,000 美元，视机器人类型和服务级别而定。

同时，商业地板清洁 AMR 等非人形机器人在 2025–2026 年的 RaaS 月费约为 450–1,200 美元，酒店清洁机器人租赁则约为 1,500–2,000 美元/月，费用通常包含维护与技术支持。工业机器人 RaaS 典型月费案例约 2,000 美元，供应商负责安装、维护和远程监控。这些数据表明，非人形 AMR 的 RaaS 模式相对成熟，人形 Digit 等仍处于早期、价格区间较高的探索阶段。

### 3.4 服务机器人：清洁、配送与行业特化

服务机器人领域的具身智能应用包括清洁机器人、酒店服务机器人、餐饮配送机器人等。Commercial Robot Vacuums、RobotLAB 和 IndustryX.ai 等分析文章给出清洁 AMR 的 RaaS 价格区间及成本结构，说明服务机器人在 RaaS 与租赁模式上的成熟度较高。

Richtech Robotics 的 IPO 招股书披露，2022 年公司收入中约 62% 来自机器人产品销售，31% 来自机器人服务（包括 RaaS、软件订阅和运维等），相比 2021 年几乎全部来自产品销售的结构，服务收入占比显著上升。公司在 10-K 年报中明确提出战略转型，从传统产品销售模式向 RaaS 模式转变，通过订阅和长期服务协议获取更可预测的经常性收入。  

Serve Robotics 的 SEC 披露文件显示，公司除了硬件收入外，已开始获得软件服务收入，某报告期软件服务收入约 0.85（单位可能为百万美元），被视为收入增长驱动之一。2026 年 Q1 业绩报道指出，其约 2.98 百万美元收入主要来自机器人交付及相关服务，软件订阅占比较小但增速较高。

这些案例说明，在服务机器人领域，硬件+服务/RaaS 的混合收入模式已开始形成，具身智能系统逐步从一次性设备销售转向订阅和服务驱动。

---

## 第四章 商业化模式与收入结构

### 4.1 商业化阶段：从原型与试点向早期量产过渡

综合中国信通院报告、各类企业和投研文章，2020–2025 年人形及通用具身智能系统整体仍处于“技术验证+小规模试点”阶段[4][7]。  
- Figure、1X 等公司在 2025–2026 年前后仍以展示性部署和少量客户项目为主，收入规模有限；  
- Agility Digit 的 GXO 部署被视为“首个正式工作”的人形 RaaS 案例；  
- Unitree 等公司的人形业务收入主要来自科研和展示市场，而非大规模工业部署。

因此，从整体产业阶段看，可以谨慎判断：具身智能商业化总体处于“小规模试点+早期量产”阶段，少数公司在特定场景实现了经常性收入，但与传统工业和服务机器人相比，具身智能尤其是人形平台的商业规模仍然有限。

### 4.2 主要商业化模式：一次性销售、RaaS、订阅与数据服务

现有证据显示，2020–2025 年具身智能商业化模式主要包括：

- 一次性设备销售（CapEx）：  
  - 传统工业机器人和四足机器人多采用一次性销售模式，部分行业盘点文章提到 Boston Dynamics Spot 等机器人的价格在十万美元级别，虽然这些数据多为估计且缺乏合同细节。
  - Unitree 等公司的人形和四足机器人收入结构仍以硬件销售为主，软件与服务收入占比较低。

- Robot-as-a-Service（RaaS）和租赁（OpEx）：  
  - Agility 与 GXO 的 Digit 多年期协议是典型人形 RaaS 案例，但具体费率和合同条款未披露。
  - 1X NEO 家用人形机器人采用每月 499 美元订阅模式，至少 6 个月承诺期，用户在不再需要时可归还机器人，体现“租赁+订阅”模式[111][112][114][115][117][118]。
  - 工业和物流类人形 RaaS 月费区间多在 2,000–15,000 美元，具体视机器人和服务支持级别而定。
  - 商用地板清洁 AMR 与酒店清洁机器人收费在 450–1,200 美元/月和 1,500–2,000 美元/月之间，通常包含维护和技术支持。
  - IndustryX.ai 指出，工业机器人 RaaS 月费约 2,000 美元，供应商负责安装、维护和远程监控。

- 软件订阅与数据服务：  
  - Richtech 将“机器人服务”（包括 RaaS、软件订阅、运维）定义为独立收入项，2022 年占比达 31%。
  - Serve Robotics 的软件服务收入约 0.85（单位可能为百万美元），被视为收入增长的重要来源之一。
  - 大模型与具身系统的一体化方案中，未来潜在的数据采集、标注和世界模型训练服务也被视为业务模式，但当前公开数据有限。

总体而言，具身智能尤其是人形机器人，正在快速从一次性硬件销售向 RaaS 和软件订阅模式迁移，但价格区间和合同结构仍不统一，具体收入模型高度依赖场景和客户类型。

### 4.3 收入结构与演化趋势：硬件 vs 服务/RaaS/订阅

Richtech 是目前公开信息中少数披露详细收入结构的公司之一。其 IPO 招股书显示，2022 年约 62% 收入来自机器人产品销售，31% 来自机器人服务（含 RaaS、软件订阅和运维），相比 2021 年几乎全部依赖产品销售，服务收入占比显著提升。10-K 年报进一步指出，公司正在战略性转型至 RaaS 模式，以获取更可预测的经常性收入流。

Serve Robotics 的 SEC 文档则表明，公司已经开始通过软件服务获得收入，且该部分收入被视为增长驱动因素之一，虽然当前总体规模仍小于硬件收入。

Hello China Tech 和 TechFlow Post 对 Unitree IPO 数据的分析显示，其收入结构仍高度依赖硬件销售，尤其是四足机器人产品线，人形产品线占比较小且主要面向科研与展示客户，软件和服务性收入占比有限。  

综合这些案例，可以得出定性判断：  
- 传统服务机器人公司已经在向“硬件 + 服务/RaaS + 软件订阅”的混合收入结构演化；  
- 人形与通用具身智能公司（Figure、1X、Agility 等）大多尚处于收入起步阶段，RaaS 和订阅模式在业务模型中占据重要位置，但尚缺乏大规模公开财务数据支撑其长期结构。

### 4.4 商业落地障碍与失败/未规模化案例类型

现有文献与行业报告指出多方面障碍：

- 成本与 ROI：  
  - 人形仓储机器人当前运营成本约为 10–12 美元/小时，预计规模化后可降至 2–3 美元/小时，但与当前劳动力成本和传统自动化系统相比，短期内经济性仍不确定。  
  - Scientific Reports 关于建筑行业的综述指出，经济性和投资回报尚不确定是许多项目在试点后被延期或缩减的重要原因。

- 安全与可靠性：  
  - 建筑工地“复杂、非结构化且快速变化”的环境对人形机器人的感知和移动能力构成重大挑战，严格的安全标准和法规显著增加系统复杂度与部署成本。  
  - A3 和 AUVSI 等组织指出，美国在安全、责任和劳动力培训等机制上缺乏统一协调，需要通过国家战略改善[74][75][76][77][88][89]。

- 场景复杂度与任务抽象：  
  - 建筑业人形机器人项目常因与熟练工人协作难度大、技能抽象困难而被“延迟、缩减或转向更专用的施工机器人形式”。  
  - 2025 年行业报告指出，传统 IL/RL 在任务变体面前需重新设计奖励或策略，感知、认知与行动割裂，导致在复杂任务中迁移不稳定[28][37]。

- 供应链与政策风险：  
  - 美国 Humanoid ROBOT Act 通过限制来自“关注国家”的人形机器人参与联邦采购，体现出地缘政治和供应链安全对具身智能商业化的潜在影响[78][79][80][81]。

这些因素共同导致许多项目停留在试点阶段或转向非人形、专用机器人形态。当前成功商业案例多集中在相对结构化的仓储、物流和清洁场景。

---

## 第五章 融资格局与团队特征

本章内容受限于图谱中已有公开报道，许多人形/具身公司详细的轮次、金额和估值尚未完全披露，以下分析以 Figure、1X、Agility 等为主，强调数据有限。

### 5.1 代表性公司的融资历程与估值

- **Figure AI**：  
  华尔街日报报道，Figure 在 2025 年寻求以约 395 亿美元估值融资约 15 亿美元[104][105]；Business Insider 稍后报道其最新估值约为 390 亿美元[103]。图谱中将两者间的 5 亿美元差异标注为“轻微估值差异”，可能反映不同时间点或轮次的估值口径[106]。  
  Business Insider 文章还提到 Figure CEO Brett Adcock 设立了新的 7 亿美元硬件基金，以支持相关生态[100]（该基金规模信息出现在新闻描述中，但未在图谱中提供进一步细节）。

- **1X Technologies**：  
  Tech Funding News 报道，OpenAI Startup Fund 在 2023 年领投了 1X 的一轮融资，金额约 2350 万美元[119][120][121]。这表明大模型公司开始通过资本布局具身智能，1X 成为其样本之一。

- **Agility Robotics**：  
  在现有图谱中，Agility 的详细融资轮次与估值数据未被收录，公开材料更多聚焦 Digit 的技术与商业化进度，以及与 GXO、Amazon 的合作[124][125]。因此本报告无法给出更精确的融资数字，仅能定性判断其已获得足以支撑生产部署和 RaaS 模式的资本支持。

- **Unitree/优必选等**：  
  优必选在公司介绍中强调自身为“全球极少数具备人形机器人全栈能力”的公司之一[54][55]，但图谱中缺乏直接融资数据。Unitree 的 IPO 披露为其收入结构提供了信息，资本层面则主要体现在其上市活动本身，详细估值与发行规模在本图谱中未展开。

总体而言，Figure 的估值在媒体报道中占据头部位置；1X 获得大模型基金的青睐；Agility 通过与头部客户签署 RaaS 合同体现出资本市场对其商业模式的认可。由于样本有限，难以系统总结全球具身智能公司的估值区间和融资密度。

### 5.2 创始人及核心技术团队背景特征

本图谱中关于创始人、核心技术负责人背景的信息非常有限，主要通过间接信号推断：

- Figure 的 Helix 模型和仓储应用场景表明，其团队在 VLM/VLA 与机器人控制上的跨界能力较强，但具体成员背景未被引用。  
- 1X 与 OpenAI Startup Fund 的合作，体现出其与大模型生态的联系[119][120][121]；Forbes 对 NEO 手部技术的报道强调工程团队在高自由度机械手设计方面的实力[124][125]，但未列出具体成员履历[124][125]。  
- 优必选强调“仿人大脑”和运动控制等全栈能力[54][55]；傅利叶 GR-1 纯视觉方案的技术文章说明其团队在 BEV+Transformer 感知和自动驾驶技术迁移方面具备经验[48][49][50][51]。  
- 阿里通义千问的具身智能小组由多模态大模型团队转型而来，反映团队从自然语言处理、深度学习背景向具身智能扩展[35][36]。

整体看，当前具身智能创业公司核心团队多具有自动驾驶、机器人控制和大模型三方面的交叉背景，但由于图谱缺乏详细个人履历数据，本报告不对具体团队结构做进一步推断。

### 5.3 投融资特点与区域差异（数据有限）

在区域层面：

- 中国通过将 physical AI/embodied AI 列入国家关键技术方向、制定具身智能路线图等方式，引导资本和产业资源流向具身智能和智能机器人领域[58][59][64][65][66][67][10][11][12][13][68][69]。券商研究报告估计中国具身智能市场已达数千亿元规模[68][69]，说明国内资本市场对该赛道认知度较高。  
- 美国则更多通过政策倡导和安全立法，以国家战略、供应链安全和防范竞争对手为主线，推动对 physical AI 的投资[70][71][72][73][74][75][76][77][82][83][78][79][80][81]。OpenAI Startup Fund 对 1X 的投资是大模型公司进入具身领域的代表案例[119][120][121]。  
- 欧洲和日本则通过机器人与具身智能科技规划、市场发展预测等形式，强调提升产业竞争力和经济转型，但公开的具体风投数据有限[14][15][16][84][85][86][87][88][89]。

由于本次图谱缺乏系统性的融资数据库，本节仅能做上述定性概括。

---

## 结语：阶段性研判与未来 3–5 年展望（在证据基础上的谨慎推演）

### 6.1 2020–2025 阶段性研判

基于上述证据，可以对 2020–2025 年全球具身智能的发展阶段做出如下审慎判断：

1. **技术路线层面**：  
   - 五大路线（大模型+机器人、RL/IL、端到端视觉到控制、经典控制+AI 混合、世界模型+仿真）已经形成清晰格局[4][7][3][5][6][22][24][28][31][32][38][39][40][41]。  
   - 实际工业系统中，分层决策+大模型辅助是主流，大模型承担需求理解、任务分解和规划生成，低层控制仍依赖传统控制与学习控制[22][23][24][25][20][21]。  
   - 端到端路线在 Tesla Optimus、Wayve、傅利叶 GR-1 等项目中被积极探索，但在精细操作和安全性方面尚存在明显不足[20][21][42][43][44][45][46][47][48][49][50][51]。

2. **产业与政策层面**：  
   - 中国在具身智能/智能机器人领域的政策信号强烈，将其上升为国家战略核心之一，并通过路线图和产业政策推动服务、工业、人形等赛道发展[58][59][64][65][66][67][10][11][12][13][68][69]。  
   - 美国则处于国家战略规划与安全立法阶段，通过 SCSP、A3、AUVSI 等组织推动 national robotics strategy，同时通过 Humanoid ROBOT Act 强化供应链安全[70][71][72][73][74][75][76][77][82][83][78][79][80][81]。  
   - 欧洲与日本以产业竞争力和国际合作为主要目标，通过科技规划与市场预测支持具身智能发展[14][15][16][84][85][86][87][88][89]。

3. **商业化与市场层面**：  
   - 整体商业阶段仍处于“小规模试点+早期量产”。  
   - 非人形 AMR 和清洁机器人在 RaaS、租赁、订阅等模式上较为成熟，而人形机器人（Figure、1X、Agility、优必选等）的商业化进展主要集中在少数标志性项目（GXO Digit、Zeekr 工厂等）和家用/演示场景[60][61][62][63][111][112][114][115][117][118]。  
   - 收入结构正在从单一硬件销售向硬件+服务/RaaS+软件订阅演化，Richtech 和 Serve Robotics 的财务数据为这一趋势提供了量化佐证。

4. **应用场景与难点**：  
   - 仓储和物流是当前人形与非人形具身智能最具落地代表性的场景，Digit 与 AMR 的协同是典型范例。  
   - 建筑和复杂工业场景由于环境非结构化、安全法规严苛和 ROI 不确定等因素，人形机器人项目普遍难以规模化。  
   - 家用人形机器人仍处于高价+订阅模式的探索阶段，市场接受度和长周期可靠性尚缺乏数据支撑[111][112][114][115][117][118]。

### 6.2 对未来 3–5 年的谨慎展望（基于现有证据的条件推演）

在强调不确定性的前提下，结合现有证据可进行以下适度推演：

1. **技术融合深化**：  
   - 大模型+RL/IL+世界模型的综合架构将进一步成为具身智能研究的主流方向，相关白皮书和指南已经系统梳理这一演进路径[5][6][8][9][31][32][38][39][40][41]。  
   - 在工业和安全敏感场景，分层架构和经典控制+AI 混合路线将持续占主导，端到端大模型控制更多用于特定子任务和实验系统[22][23][24][25][20][21]。

2. **RaaS 与订阅模式扩展**：  
   - 现有 RaaS 价格区间和成功案例（Digit-GXO、清洁 AMR、工业 RaaS 等）提供了参考框架。  
   - 随着规模化部署，单位小时成本预计下降（如 Digit 类人形机器人成本从 10–12 美元/小时向 2–3 美元/小时下行）的预期，但这一降幅和时间表仍受技术、供应链和市场需求影响。

3. **政策与监管趋于细化**：  
   - 中国和美国已经分别通过路线图和国家战略备忘录对具身智能提出了方向性规划[58][59][64][65][66][67][10][11][12][13][70][71][72][73]；未来 3–5 年，相关政策预计会在安全标准、责任分配、数据治理和供应链安全等方面进一步细化。  
   - 美国 Humanoid ROBOT Act 显示，人形机器人已经被纳入国家安全考量[78][79][80][81]；类似法律与监管安排可能在其他国家陆续出现。

4. **商业模式与收入结构进一步多元化**：  
   - 以 Richtech 和 Serve 为代表的公司已经展现从硬件销售向服务型收入转型的路径；这一趋势在具身智能领域预计将扩展到更多企业。  
   - 对于 Figure、1X 和 Agility 等人形公司，由于当前缺乏系统财务披露，未来 3–5 年其收入结构和毛利模式仍存在较大不确定性，尤其是在 RaaS 定价、软件订阅与数据服务的占比方面。

### 6.3 数据缺口与不确定性

本报告基于图谱中已收集文献，存在以下局限：

- **时间与样本覆盖**：  
  - 许多关键事件发生在 2024–2026 年边界，部分数据处于早期或试点阶段，难以形成长期趋势判断。  
  - 对韩国及部分欧洲国家的具身智能创业公司和政策信息收集较少，区域比较存在不均衡。

- **财务与商业细节**：  
  - Figure、Agility、1X 等公司的具体收入规模、毛利结构和合同条款尚未广泛公开；现有信息多来自媒体报道，难以全面反映其商业模式。  
  - RaaS 价格与成本数据多为行业估计和范围值，且针对的产品和服务组合不完全一致，使用时需谨慎。

- **技术架构透明度**：  
  - 许多人形和具身系统的具体控制架构、大模型参数和安全机制属于商业机密，仅通过专利、案例和媒体间接披露，本报告只能在已有证据框架内做结构性概括，而不能给出细粒度技术细节。

在这些不确定性条件下，本报告强调对未来的判断应保持谨慎。对于关注具身智能的投资人与产业研究者而言，更适合将本报告视作“技术路线与商业模式的结构化框架”，而非精确的数值预测工具。后续研究可在本框架基础上，结合更多财务披露和技术白皮书，持续更新对具身智能产业的认知。

---

## 参考文献

[1] 2025商用具身智能白皮书 https://pdf.dfcfw.com/pdf/H3_AP202512031793353788_1.pdf?1764833841000.pdf

[2] 甲子光年智库智库院长：宋涛报告撰写：翟惠宇发布时间 - 信息资源系统 https://28254755.s21i.faiusr.com/61/ABUIABA9GAAgmcKqvQYomLfimwU.pdf

[3] 具身智能产业发展现状与趋势调研报告 https://file.jgvogel.cn/125/upload/resources/file/650706.pdf

[4] 具身智能发展报告 - 中国信息通信研究院 http://www.caict.ac.cn/kxyj/qwfb/bps/202601/P020260130541978285206.pdf

[5] 2025深圳具身智能机器人产业：从技术热潮到应用落地 https://fgw.sz.gov.cn/ztzl/qtztzl/szscjmyjjfzzhfwpt/xwdt/content/post_12623411.html

[6] 走进更多生活场景“具身智能”机器人如何越来越聪慧 https://www.cac.gov.cn/2025-09/18/c_1759916098343469.htm

[7] Will embodied AI create robotic coworkers? https://www.mckinsey.com/industries/industrials/our-insights/will-embodied-ai-create-robotic-coworkers

[8] Embodied AI with Foundation Models for Mobile Service Robots https://www.mdpi.com/2218-6581/15/3/55

[9] Humanoid Robots at Work [2026 Guide] https://blog.robozaps.com/b/humanoid-robots-in-workplace

[10] What Is Figure AI? https://builtin.com/articles/figure-ai

[11] 30+ Humanoid Robot Companies Ranked [2026] https://blog.robozaps.com/b/humanoid-robot-companies

[12] Physical AI https://mlq.ai/research/physical-ai/

[13] Embodied Intelligence Is Redefining Industrial Operations https://www.techaheadcorp.com/blog/how-embodied-intelligence-redefining-industrial-operation/

[14] Paper List and Resource Repository for Embodied AI https://github.com/HCPLab-SYSU/Embodied_AI_Paper_List

[15] 参考400文献的综述：具身智能综述——连接网络空间与物理世界 https://www.pnprobotics.com/sys-nd/75.html

[16] 具身智能发展报告 https://www.caict.ac.cn/kxyj/qwfb/bps/202408/P020240830312499650772.pdf

[17] 面向柔性制造的具身智能综述 https://robot.sia.cn/cn/article/pdf/preview/10.13973/j.cnki.robot.250208.pdf

[18] 中国人工智能系列白皮书—-具身智能(2026 版) https://ceai.caai.cn/static/upload/file/20260412/1775977669687642.pdf

[19] 基于大模型的具身智能系统综述 http://www.aas.net.cn/cn/article/doi/10.16383/j.aas.c240542

[20] 大模型赋能的具身人工智能：决策与具身学习综述(上) https://zhuanlan.zhihu.com/p/1942709414734861477

[21] 大模型时代的具身智能（张伟男：具身大模型关键技术与应用） https://ssatt.bj.bcebos.com/2024/%E5%BC%A0%E4%BC%9F%E7%94%B7%EF%BC%88%E5%93%88%E5%B0%94%E6%BB%A8%E5%B7%A5%E4%B8%9A%E5%A4%A7%E5%AD%A6%EF%BC%89%EF%BC%9A%E5%85%B7%E8%BA%AB%E5%A4%A7%E6%A8%A1%E5%9E%8B%E5%85%B3%E9%94%AE%E6%8A%80%E6%9C%AF%E4%B8%8E%E5%BA%94%E7%94%A8.pdf

[22] What is Embodied AI? A Guide to AI in Robotics https://encord.com/blog/embodied-ai/

[23] 2025年具身智能行业研究（含模仿学习和强化学习的局限分析） https://pdf.dfcfw.com/pdf/H3_AP202509041738887829_1.pdf

[24] 特斯拉机器人全面进化！感知、大脑、运动控制能力升级端到端方案 … https://m.cls.cn/detail/1471518

[25] 2021~2025：特斯拉人形机器人Optimus发展进程详解 https://zhuanlan.zhihu.com/p/1908561554837868813

[26] The Road to Embodied AI https://wayve.ai/thinking/road-to-embodied-ai/

[27] [论文评述] A Survey: Learning Embodied Intelligence from Physical Simulators and World Models https://www.themoonlight.io/zh/review/a-survey-learning-embodied-intelligence-from-physical-simulators-and-world-models

[28] 南京大学具身机器人万字长文全面综述！从物理模拟器和世界模型中 ... https://zhuanlan.zhihu.com/p/1925645011027986125

[29] Embodied AI: China's Big Bet on Smart Robots https://carnegieendowment.org/research/2025/11/embodied-ai-china-smart-robots

[30] 2024年中国具身智能行业研究 https://pdf.dfcfw.com/pdf/H3_AP202408121639245277_1.pdf

[31] Europe Embodied AI Market Size to Reach USD 8.7 Bn by 2034 https://dimensionmarketresearch.com/report/europe-embodied-ai-market/

[32] Figure AI 官方网站 https://www.figure.ai/

[33] Helix: A Vision-Language-Action Model for Generalist Humanoid Robots https://www.figure.ai/news/helix

[34] 阿里通义组建机器人和具身智能团队，要让智能体具备“行动力” https://www.stcn.com/article/detail/3369484.html

[35] 阿里入局具身智能：大模型的“物理世界”革命 https://aistudio.baidu.com/blog/detail/731285778975941

[36] 具身智能技术指南 Embodied-AI-Guide https://github.com/tianxingchen/Embodied-AI-Guide

[37] AI & Robotics | Tesla https://www.tesla.com/AI

[38] A Complete Review Of Tesla's Optimus Robot https://briandcolwell.com/a-complete-review-of-teslas-optimus-robot/

[39] Figure 01 https://robotsguide.com/robots/figure

[40] 1X | Home Robots https://www.1x.tech/

[41] NEO Home Robot https://www.1x.tech/neo

[42] Agility Robotics https://www.agilityrobotics.com/

[43] Humanoid Robot 'Digit' – Whole-Body Control Foundation Model https://www.nvidia.com/en-us/case-studies/agility-robotics-digit-humanoid-robot/

[44] Open X-Embodiment: Robotic Learning Datasets and RT-X Models https://robotics-transformer-x.github.io/

[45] Scaling up learning across many different robot types https://deepmind.google/blog/scaling-up-learning-across-many-different-robot-types/

[46] Amazon announces new fulfillment center robots, Sequoia and Digit https://www.aboutamazon.com/news/operations/amazon-introduces-new-robotics-solutions

[47] Atlas Humanoid Robot https://bostondynamics.com/products/atlas/

[48] 关于优必选科技 https://www.ubtrobot.com/cn/about/company-profile?srsltid=AfmBOopH7Z_aUgcR-VGVIJs_Di8CQmnkYkYo5NOl8iNeW0XURWhLW8X5

[49] 傅利叶GR-1半年进阶实录：迈向具身智能下一阶段 https://www.fftai.cn/about-medium-technical/3

[50] 杭州云深处科技-具身智能技术创新与行业应用引领者 https://www.deeprobotics.cn/

[51] GXO Signs Industry-First Multi-Year Agreement with Agility Robotics https://www.agilityrobotics.com/content/gxo-signs-industry-first-multi-year-agreement-with-agility-robotics

[52] Agility Robotics’ Digit humanoid lands first official job https://www.therobotreport.com/agility-robotics-digit-humanoid-lands-first-official-job

[53] Digit Deployed at GXO in Historic Humanoid RAAS Agreement https://www.agilityrobotics.com/content/digit-deployed-at-gxo-in-historic-humanoid-raas-agreement

[54] https://www.me.news/contents/279851 https://www.me.news/contents/279851

[55] Global Commercial Humanoid Robotics Market Research 2025 … https://finance.yahoo.com/sectors/technology/articles/global-commercial-humanoid-robotics-market-113500134.html

[56] Sam Altman’s OpenAI just made robotics its next frontier and it’s hiring to prove it https://techfundingnews.com/sam-altmans-openai-just-made-robotics-its-next-frontier-and-its-hiring-to-prove-it/

[57] Top 10 robotics stories of May 2026 https://www.therobotreport.com/top-10-robotics-stories-of-may-2026/

[58] This Robot Might Have The Best Hands Of Any Humanoid Ever https://www.forbes.com/sites/johnkoetsier/2026/06/01/this-robot-might-have-the-best-hands-of-any-humanoid-ever/

[59] The $40 Billion Startup Mystery Shaking Up Silicon Valley https://www.wsj.com/tech/the-hottest-pre-ipo-stock-an-ai-robotics-startup-with-bold-claims-little-revenue-b0c1f03b

[60] Silicon Valley's new slogan: Let's get physical https://www.businessinsider.com/silicon-valleys-new-slogan-lets-get-physical-2026-6

[61] Tesla Optimus Gen 3: Inside the Humanoid Robot Revolutionizing Industry https://ts2.tech/en/tesla-optimus-gen-3-inside-the-humanoid-robot-revolutionizing-industry/

[62] ‘The Great Replacement’: 5 robots replacing human workforce in 2026 https://www.wionews.com/photos/the-great-replacement-5-robots-replacing-human-workforce-in-2026-1780553633059

[63] Agility Robotics Stock / IPO (title approximate, financing overview) https://accessipos.com/agility-robotics-stock-ipo/

[64] Humanoid Robots: From Demos to Deployment https://www.bain.com/insights/humanoid-robots-from-demos-to-deployment-technology-report-2025/

[65] Humanoid Robots https://www.uscc.gov/sites/default/files/2024-10/Humanoid_Robots.pdf

[66] Embodied AI Market Report 2025 - 2030 [291 Pages & 249 Tables] https://www.marketsandmarkets.com/Market-Reports/embodied-ai-market-83867232.html

[67] Embodied AI Market 2033: Latest Trends, Growth Potential & Future … https://www.congruencemarketinsights.com/report/embodied-ai-market

[68] Logistics Robots Market Size, Share & Trends Report 2034 https://www.imarcgroup.com/logistics-robots-market

[69] Warehouse Robotics Market Size & Opportunities, 2026-2033 https://www.coherentmarketinsights.com/market-insight/warehouse-robotics-market-5056

[70] Humanoid Service Robots: The Future of Healthcare? https://www.researchgate.net/publication/349948626_Humanoid_Service_Robots_The_Future_of_Healthcare

[71] Humanoid Robots in Healthcare: The Future is Here—But Are We Ready? https://ache-cahl.org/articles/humanoid-robots-in-healthcare-the-future-is-here-but-are-we-ready/

[72] Embodied AI: China’s ambitious path to transform its robotics industry https://merics.org/en/report/embodied-ai-chinas-ambitious-path-transform-its-robotics-industry

[73] China Makes AI-powered Robots Core of National Strategy https://ifr.org/ifr-press-releases/news/china-makes-ai-powered-robots-core-of-national-strategy

[74] China Just Made Physical AI the Center of Its Economy. What's ... https://sixdegreesofrobotics.substack.com/p/china-just-made-physical-ai-the-center

[75] Memos to the National Robotics Strategy https://www.scsp.ai/wp-content/uploads/2025/02/Robotics-Memo.pdf

[76] Embodied AI: How the US Can Beat China to the Next Tech Frontier https://www.hudson.org/embodied-ai-how-us-can-beat-china-next-tech-frontier-michael-sobolik

[77] A3 Policy Recommendations and Advocacy Principles for the U.S. – A3’s Vision for a U.S. National Robotics and Automation Strategy https://www.automate.org/a3/advocacy-principles

[78] Robot Ready: The U.S. Needs a National Robotics Strategy Now https://www.auvsi.org/robot-ready-the-u-s-needs-a-national-robotics-strategy-now

[79] Text of S. 3275: Humanoid ROBOT Act of 2025 https://www.govtrack.us/congress/bills/119/s3275/text

[80] Integration of Embodied AI and Robotics - CRDS-FY2025-SP-01 https://www.jst.go.jp/crds/en/publications/CRDS-FY2025-SP-01.html

[81] Embodied AI and General Purpose Robots https://gerard-de-valence.blogspot.com/2025/11/embodied-ai-and-general-purpose-robots.html

[82] Pudu Robotics: Global Service Robot Leader https://www.scribd.com/document/971959293/Pudu-Robotics-Company-Introduction-PPT-V4-0-20241107-EN

[83] PUDU Robotics Leads Global Commercial Robot Market with 23% Share https://www.linkedin.com/posts/trenaissance_commercialrobotics-b2bhardware-embodiedai-activity-7431506982794199040-pN85

[84] Pudu Robotics Unveils New Factory, Celebrates Production of 80,000th Robot in Jiangsu, China https://www.pudurobotics.com/en/news/911

[85] THE RISE OF AI ROBOTS: Physical AI is Coming for You https://www.citifirst.com.hk/home/upload/citi_research/rsch_pdf_30297368.pdf

[86] Figure Exceeds $1B in Series C Funding at $39B Post-Money Valuation https://www.figure.ai/news/series-c

[87] Figure AI • Pre-IPO Unicorns - HUDSONPOINT capital https://hudsonpoint.com/pre-ipo/figure-ai

[88] Figure AI shares now available to accredited investors via SeedBlink’s secondary market https://seedblink.com/press-room/2025-05-16-figure-ai-shares-now-available-to-accredited-investors-via-seedblinks-secondary-market

[89] Robotics Funding Crests Higher As Figure Lands Another $1B https://news.crunchbase.com/robotics/ai-funding-high-figure-raise-data/

[90] Figure AI valuation, funding & news | Sacra https://sacra.com/c/figure-ai/

[91] Brett Adcock - Wikipedia https://en.wikipedia.org/wiki/Brett_Adcock

[92] Master Plan - Figure AI https://www.figure.ai/master-plan

[93] Brett Adcock - Founder @ Figure, Hark, Cover, & Archer Aviation https://www.linkedin.com/in/brettadcock

[94] 1X Raises $23.5M in Series A2 Funding led by OpenAI https://www.1x.tech/discover/1x-rasies-23-5m-in-series-a2-funding-led-by-open-ai

[95] 1X Secures $100M in Series B Funding https://www.1x.tech/discover/1x-secures-100m-in-series-b-funding

[96] Norwegian Robotics Startup 1X Secures $100M in Series B Funding Led by EQT Ventures https://eqtgroup.com/en/thinq/early-stage/norwegian-robotics-startup-1x-secures-100m-in-series-b-funding-led-by-eqt-ventures

[97] 1X Technologies funding, news & analysis | Sacra https://sacra.com/c/1x-technologies/

[98] 1X Business Breakdown & Founding Story - Contrary Research https://research.contrary.com/company/1x

[99] 1X Technologies - Wikipedia https://en.wikipedia.org/wiki/1X_Technologies

[100] Agility Robotics Raises $150M Series B Led By DCVC and Playground Global https://www.agilityrobotics.com/content/agility-robotics-raises-150m-series-b-led-by-dcvc-and-playground-global

[101] ONAMI Gap Company Agility Robotics Secures $8M Series A Funding https://onami.us/onami-success-stories/agility-robotics-secures-8m-series-a-funding

[102] Agility Robotics: Investor Insights - Acquinox Capital https://acquinox.capital/insights/gen-ai-and-ai-agents/agility-robotics-investor-insights

[103] Agility Robotics valuation, funding & news | Sacra https://sacra.com/c/agility-robotics/

[104] Agility Robotics Stock: $2.1B Valuation — Is It a Buy? | TSG Invest https://tsginvest.com/agility-robotics/

[105] Company - Agility Robotics https://www.agilityrobotics.com/company

[106] Agility Welcomes Robotics Pioneer Melonee Wise as New CTO, Establishes New Chief Robot Officer Role... https://www.agilityrobotics.com/content/agility-welcomes-robotics-pioneer-melonee-wise-as-new-cto-establishes-new-chief-robot-officer-role-and-celebrates-year-of-outstanding-leadership-growth

[107] Damion Shelton - Co-founder and Chairman at Agility Robotics https://www.linkedin.com/in/damion-shelton

[108] Spotlight: Jonathan Hurst - Oregon Journalism Project https://www.oregonjournalismproject.org/spotlight-jonathan-hurst

[109] Report: Agility Robotics' Business Breakdown & Founding Story https://research.contrary.com/company/agility-robotics

[110] Tesla’s Self-Driving is Betting on the Scaling Hypothesis https://brief.bismarckanalysis.com/p/teslas-self-driving-is-betting-on

[111] Tesla Dojo: The rise and fall of Elon Musk’s AI supercomputer https://techcrunch.com/2025/09/02/tesla-dojo-the-rise-and-fall-of-elon-musks-ai-supercomputer/

[112] Order NEO https://www.1x.tech/order

[113] 1X has launched NEO, a humanoid household robot. Here's how to ... https://mashable.com/article/1x-neo-humanoid-robot-preorder

[114] For $20,000, a humanoid robot will do your household chores for you https://fortune.com/2026/02/26/humanoid-robot-that-will-do-chores-for-you-robotics-company-1x/

[115] Are You Ready To Buy Humanoid Robots On A Subscription Plan? https://www.getmonetizely.com/blogs/are-you-ready-to-buy-humanoid-robots-on-a-subscription-plan

[116] The Real Cost of Robot Cleaners: 2026 Pricing, RaaS, and Hidden Fees https://commercialrobotvacuums.com/real-cost-of-commercial-robotic-floor-cleaners

[117] What are the most affordable cleaning robot solutions for hotels https://www.robotlab.com/group/blog/what-are-the-most-affordable-cleaning-robot-solutions-for-hotels

[118] Industrial Robots Guide: Types, ROI & Costs (2026) https://industryx.ai/2025/12/04/industrial-robots-guide-2025/

[119] Humanoid Robot Cost 2026: Complete Price & ROI Breakdown https://www.theresarobotforthat.com/blog/humanoid-robot-cost-roi-breakdown/

[120] f424b41123_richtech.htm https://www.sec.gov/Archives/edgar/data/1963685/000121390023088748/f424b41123_richtech.htm

[121] Form 10-K — Richtech Robotics INC https://www.sec.gov/Archives/edgar/data/1963685/000121390025003458/ea0226831-10k_richtech.htm

[122] SEC Filing — Serve Robotics https://investors.serverobotics.com/node/7191/html

[123] Serve Robotics Q1 2026 revenue surges but losses widen https://www.stocktitan.net/sec-filings/SERV/10-q-serve-robotics-inc-de-quarterly-earnings-report-b04c8194c187.html

[124] Unitree's $610M IPO Shows What Humanoid Robotics Really Sells https://hellochinatech.com/p/unitree-ipo-humanoid-robotics-really-sells

[125] Decoding Unitree's IPO Prospectus: The Real Landscape of the ... https://www.techflowpost.com/en-US/article/31730

[126] Opportunities, challenges and roadmap for humanoid robots in construction https://www.nature.com/articles/s41598-025-30252-6
