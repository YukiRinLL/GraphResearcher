## 全球具身智能技术路线与代表性公司研究报告（2024–2026）

### 引言

本报告聚焦 2024–2025 年（个别延伸至 2026 年）的全球具身智能发展，系统梳理主要技术路线及其代表性公司，重点覆盖以下四条主线：[1]

- 通用人形机器人  
- 机器人基础模型 / 视觉-语言-动作模型（VLA）与世界模型  
- 轮式 / 轮足移动操作及仓储物流  
- 灵巧操作与末端执行器  

研究方法基于公开资料汇总，包括企业官网、新闻稿、财报与招股书、投资与产业研究机构报告、主流媒体及专业技术博客等，所有事实性陈述均可追溯至具体来源。[2][3][4]

关键假设与局限：

1. **时间窗口**：  
   信息主要集中在 2024–2025 年，部分人形机器人和基础模型路线延伸至 2026 年（如 Boston Dynamics 电动 Atlas 在 2026 年 CES 公告转向产品化，[3] Sanctuary 在 2026 年获得 Zeon Ventures 投资等[5]）。

2. **信息不对称与口径差异**：  
   - 部分公司对部署规模、融资总额仅给出区间或定性描述，例如 Agility Robotics 总融资额在不同数据源中存在明显差异（2.88 亿美元 vs 约 6.4 亿美元），本报告采用区间表述。[6]  
   - Figure 与 BMW 合作的实际部署规模存在官方与第三方媒体表述差异：Figure 官方强调“参与生产 30,000 辆车”，BMW 官方将项目定义为“试点”，媒体称截至 2025 年 3 月仅一台机器人在夜班测试，本报告在相关段落中据实并列。[7][8]

3. **地域与样本覆盖**：  
   报告聚焦美国、加拿大、欧洲和中国等具身智能热点地区的代表公司；对部分日本、韩国及中小企业因资料有限未做系统覆盖。

4. **技术与商业边界**：  
   - “具身智能”在本报告中指“机器人硬件 + 基础模型/VLA + 仿真与世界模型”的综合体系。[1]  
   - 商业化部分优先关注进入真实场景试点、产生收入或签署多年协议的项目，而非一次性演示。

---

## 第一章 全球具身智能主要技术路线总览

### 1.1 人形机器人路线

通用人形机器人在形态上接近人类尺寸，通常具备双臂、躯干、头部以及双足或腿+轮组合，拥有多自由度关节、全身动力学与平衡控制能力，目标是在“为人而建”的环境中执行多任务。[1] 传感侧采用多摄像头、力/扭矩传感器等，控制侧逐步引入大语言模型（LLM）、视觉-语言模型（VLM）和 VLA 进行任务理解与规划。[1]

典型应用场景包括：

- 工业与物流：在汽车和 3C 离散制造中进行物料搬运与装配辅助，在仓储物流中执行拣选和搬运等任务。[1][9]  
- 服务与家庭：家务、养老、导览等，目前多为高价早期产品及展示性试点。[1][9]

发展阶段上：

- 工业/物流：2024–2025 年间，代表公司已从实验室演示进入“小规模商业试点与早期量产准备”阶段，包括人形机器人作为工作单元在工厂产线运行、在仓库以 RaaS 模式按小时计费等。[1][9][10]  
- 家庭/服务：仍主要处于高价早期产品、遥操作采数与展示性试点阶段，如 1X NEO 家用机器人、Figure 面向家庭的 Figure 03 等。[9][11][12]

整体判断：人形硬件是具身智能最直观的方向，中短期落地点仍以工业与物流为主，家庭场景更偏长期探索。[1][9]

### 1.2 机器人基础模型 / VLA 与世界模型路线

机器人基础模型与 VLA 被视为具身智能的软件内核，多数系统采用“基础模型 + 控制层”的双层架构，输入包括视觉、语言与多模态传感信号，输出关节轨迹或动作原语。[1][13]

代表系统与技术路径包括：

- Google DeepMind 的 Gemini Robotics，将物理动作作为新的输出模态直接控制机器人，推出具身推理版本（ER 1.5/1.6），在多个具身基准上相较此前 VLA 和通用多模态模型显著提升。[13][14]  
- NVIDIA Project GR00T，通过 GR00T N1/N1.5 基础模型 + Isaac 仿真 + Jetson Thor 硬件提供从仿真到训练到部署的一体化平台，GR00T-Dreams 利用合成视频和动作 token 训练搬运与排序任务。[1][15]  
- Physical Intelligence 的 π 系列（π0、π0.5、π*0.6、π0.7），定位为“Physical Intelligence Layer”，以图像+文本输入、底层电机命令输出，通过多机器人多任务数据与强化学习提供统一策略，并以模型授权或 SaaS 为主要商业模式。[1][16]  
- Figure 的 Helix，将感知、语言理解和控制统一在单一网络中，实现全身多自由度高频控制，可在嵌入式低功耗 GPU 上运行，并支持两台人形协作完成多种家务任务。[1][17]  
- 开源路线如 OpenVLA + Open X-Embodiment + RT-X，提供大规模跨机器人数据集与 7B 级 VLA 模型，验证跨机器人预训练的正迁移效果。[1][18]

架构趋势方面：

- 行业逐渐形成共识：世界模型和视频预训练将成为软件栈关键组成，上层世界模型负责物理理解与长时规划，下层 VLA/控制器负责动作输出，系统结构从单一 VLA 向“世界模型 + 控制层”演进。[1][19]  
- 路线分化：一类以云端基础模型 + API 服务多种机器人（Gemini Robotics、GR00T N1.5），一类构建与自有硬件高度紧耦合的专用 VLA/世界模型（Helix、1X World Model、π 系列）。[1][13]

### 1.3 轮式 / 轮足移动操作与仓储物流路线

轮式和轮足移动操作介于传统 AGV/AMR +机械臂和人形机器人之间，使用轮式或双足底盘搭配机械臂，在仓储拣选、服务取物、科研辅助等场景执行移动抓取和取放任务，并结合导航及语义地图。[1]

技术特征与发展阶段：

- 在仓储和服务等平面环境中，轮式移动操作已进入“成熟商用 + 向具身基础模型升级”阶段，被认为是具身智能最早实现稳定盈利的路线之一。[1][20]  
- 控制从传统脚本/行为树向引入 open-vocabulary 与 VLA 的语义感知控制过渡，通过 LLM/VLM/VLA 接入复杂任务。[1][20]  
- 典型平台包括 Agility 的 Digit（既属人形路线，又是双足移动操作平台），通过 Agility Arc 云平台实现车队级监控与 WMS/WES 集成，标志从单机演示向车队运营与云端运维转变。[1][21]  
- Hello Robot Stretch + Stretch AI 被广泛用于学术与初创公司，是 open-vocabulary 移动操作与示教学习的重要标准平台之一。[1][22]

### 1.4 灵巧操作与末端执行器路线

灵巧操作聚焦多指高自由度机械手在非结构化接触、变形物体和长时任务中的控制，需高性能机械手、复杂驱动与高带宽力触觉传感，并依赖端到端 AI 模型及仿真到现实技术。[1][23]

发展阶段与技术 pipeline：

- 综述与市场报告认为灵巧操作仍处于“前沿研究 + 早期工业试点”阶段。[23]  
- 构建系统化 pipeline 的三大支柱是：高性能硬件、高保真仿真和多模态基础模型（包括 VLA 与世界模型）。[23]  
- Sanctuary AI 使用液压多指手、NVIDIA Isaac Lab 仿真与自研触觉传感器，展示零样本手内操作与复杂装配任务，是工业强度灵巧操作路线的一个代表。[1][24]  
- Figure 在 Helix-02 驱动下实现两台人形在卧室环境协同完成家具移动、挂衣、整理床铺等任务，两台机器人通过视觉观察对方动作推断意图，无显式通信或中央规划器，体现全身协作与复杂物体操作潜力。[1][25]

---

## 第二章 人形机器人路线代表性公司

选取 Figure AI、Tesla Optimus、Agility Robotics、Apptronik、Sanctuary AI、1X Technologies、UBTECH（优必选）、Unitree（宇树）、Fourier Intelligence（傅利叶）以及小米机器人团队，从技术路径、产品进度、商业化、融资与团队维度进行分析。

### 2.1 Figure AI

**技术路径与产品形态**

Figure 以通用人形机器人为核心，定位“给 AI 一个身体”，面向制造、零售和家庭等场景的劳动力缺口。[26][27] 公司自建高产量制造设施 BotQ 支持大规模生产，并以 Helix VLA 模型作为统一的感知、语言理解与控制核心。[28][29]

Helix 是通用 Vision-Language-Action 模型，输入视频与语言指令，输出全身动作控制信号，基于大规模真实世界和仿真数据（人类视频和机器人执行轨迹）进行端到端训练，而非传统“感知—规划—控制”分模块结构。[29] Helix 已用于控制 Figure 机器人完成折叠衣物、装洗碗机等家务任务，并在“Helix Learns to Fold Laundry”“Helix Loads the Dishwasher”等项目中展示家务能力。[29]

**产品与试点进度：BMW 合作的两种叙事**

Figure 02 作为第二代人形平台在 BMW Spartanburg 工厂进行长期试点：Figure 官方称 Figure 02 在装配线上连续约 10 个月、每日运行约 10 小时，累计完成超过 90,000 个零件上下料任务，并“作为人形工作单元操作员参与生产了约 30,000 辆汽车”。[1][30][31]

Figure 新闻稿还称，Figure 02 在 BMW 工厂“持续运行”，负责物料搬运与机床上下料，与人类工人协同 24/7 工作。[31]

与此相对，BMW 集团的官方新闻稿将合作描述为“试点项目”，强调这是 BMW 首次在工厂部署人形机器人，但未将其表述为大规模量产替代劳动力。[32] Fortune 报道引述 BMW 发言人称，截至 2025 年 3 月，Spartanburg 工厂仅部署了一台 Figure 机器人，主要在夜间非生产时间练习拾取和放置零部件，之后才在生产时间段执行有限任务，尚未形成 CEO 所称的“多机器人车队端到端运营”。[8][33]

合理的“区间式”理解是：

- 部署数量：截至 2025 年初，BMW 工厂现场 Figure 机器人数量约为 1 台。[8][33]  
- 工作节奏：机器人确有在真实产线执行物料搬运任务，并在一定时间内参与了数万件零件处理和数万级整车产量，但更多以高强度单机试点形式存在，其生产贡献集中在特定工位和时段。[30][31][32]  
- 结论：应将 Figure-BMW 合作视为“高强度单机试点 + 中等时长运行”的里程碑，而非已实现多机器人规模化替代人工的成熟部署。

此外，Figure 在 2024 年底向至少一位付费客户交付 Figure 02 系统，Robot Report 将其视为从研发验证进入早期付费商业部署的重要节点。[34]

**融资与估值**

- 2024 年：完成 6.75 亿美元 B 轮融资，投后估值 26 亿美元，投资方包括 Microsoft、OpenAI Startup Fund、NVIDIA 等，并宣布与 OpenAI 签署合作协议共同开发人形机器人 AI 模型。[35][36]  
- 2025 年：C 轮融资超 10 亿美元，投后估值约 390 亿美元，用于加速通用人形机器人部署、扩展 Helix 与 BotQ 产能，并加强与大型科技公司的合作。[37][38]

多源报道（公司新闻稿、媒体分析等）对 B、C 轮融资额和估值信息相互印证；Fortune 报道称 Figure 累计融资超过 7 亿美元并在洽谈估值接近 400 亿美元的新一轮，与官方 C 轮披露在数量级上基本一致。[33][37][38]

**团队背景**

Figure 由 Brett Adcock 于 2022 年创立，他此前创办并出售 AI 人才市场 Vettery（以 1.1 亿美元对 Adecco），以及电动航空公司 Archer（融资超 10 亿美元并以约 27 亿美元估值上市），具备连续创业和工程背景。[39][40] Figure 官网称团队拥有“超过 100 年的 AI 与人形经验”，强调其跨多代航空器与机器人系统的工程能力。[27][41]

**小结**

Figure 的路线典型体现“人形硬件 + 自研 VLA + 自建制造”三位一体：优势在于高强度试点、Helix 统一控制架构及巨额融资能力；风险在于当前商业部署仍以少量试点为主，BMW 合作规模存在口径差异，未来落地强度仍有不确定性。[7][8][33][34]

### 2.2 Tesla Optimus

**技术路径**

Tesla Optimus 是特斯拉提出的通用双足自主人形机器人，目标执行危险、重复或枯燥任务。其 AI 路线与特斯拉自动驾驶相似，采用基于摄像头和神经网络的视觉与规划系统，不依赖激光雷达。[42][43]

**产品与演示现状**

- 2021 年 Tesla AI Day 首次公布 Optimus 概念，2022 年展示两个样机；2023 年末展示第二代外观与动作版本；2024 年发布视频，展示在工厂执行电池分拣和搬运等任务。[44]  
- 媒体披露，在 2024 年部分活动中，Optimus 演示的拿饮料、与观众互动等动作由佩戴 VR 头显的人类远程操作完成，特斯拉回应称遥操作用于加速训练，长期目标是完全自主。[45][46]  
- 2025 年 10-K 年报中，特斯拉仍将 Optimus 视为研发阶段产品，明确其尚未产生显著收入。[47]

**商业化路线与时间表**

- BuiltIn 整理称，特斯拉计划在 2025 年开始生产 Optimus，目标售价低于 3 万美元，用例包括工厂辅助和家庭任务，但也引述外界质疑其短期实现完全通用能力的可能性。[48]  
- Musk 在 2024 年接受路透采访时表示，计划 2025 年在特斯拉工厂内部部署约 1000 台 Optimus，2026 年开始对外销售。[49]  

综合来看，Optimus 技术路线清晰但仍处内部试验与演示阶段：以视觉-first 架构和特斯拉现有 AI 平台为基础，预计先在自有工厂内部试点，短期内与 Figure、Agility、Apptronik 等相比，商业化进度更早期。[45][47][49]

### 2.3 Agility Robotics（Digit）

**技术路径与产品**

Digit 是双足加双臂的移动操作平台，面向仓储物流中的托盘和箱体搬运任务，设计在现有人类工厂环境中执行多任务。[1][50][51] Digit 在仓库内执行 tote 取放任务，与 AMR 和输送线协作，通过 Agility Arc 云平台实现车队级运营监控和与 WMS/WES 集成，体现从单机演示向车队运营与云端运维转变。[21]

**GXO 商业部署与 RaaS 模式**

- 2024 年 6 月，Digit 在 GXO 亚特兰大仓库以多年期 RaaS 协议进入日常运营，执行枯燥、肮脏、危险的搬运与拣选任务，连接自动化岛。[10][50]  
- Agility 与 GXO 声称这是“首个正式商业部署的人形机器人”和首个“humanoid RaaS 部署”，Digit 从协作臂接过周转箱并放上输送带，与现有 AMR 和自动化系统集成。[52][53]  
- Robot Report 报道 Digit 按每小时约 30 美元收费，目标在两年内帮助客户收回成本，显示其 RaaS 模式的经济性假设。[54]

**产能与工厂建设**

Agility 在俄勒冈 Salem 建设 RoboFab 工厂，面积约 70,000 平方英尺，设计年产能最高可达 10,000 台 Digit，计划自 2024 年起向“Agility Partner Program”客户交付首批 Digit。[55]

**融资与估值：区间理解**

- Startup Intros：总融资 2.88 亿美元，4 轮融资，最新为 2024 年 10 月 1 日 1.1 亿美元 C 轮。[56]  
- TSG Invest：估算截至 2025 年总融资约 6.4 亿美元，包括约 4 亿美元 C 轮，对应估值约 21 亿美元。[6][57]

由于 TSG 提供的是估算值，而 Startup Intros 统计已确认轮次，合理理解为公开确认的融资额至少在 2.88–6.4 亿美元区间，总量可能接近 6 亿美元，但具体数字存在口径差异，本报告使用“约 3–6 亿美元区间”。[6][56][57]

**团队与治理**

Agility 由 Jonathan Hurst、Damion Shelton 和 Mikhail Jones 等自俄勒冈州立大学动力机器人实验室分拆成立，2024 年后由 Peggy Johnson（前微软高管与 Magic Leap CEO）任 CEO，Pras Velagapudi 任 CTO，Daniel Diez 任 CBO。[58]

**小结**

Digit 路线体现“人形形态 + 移动操作能力 + 工业 RaaS 模式”：技术上依托 Arc 平台支持车队部署，商业上通过与 GXO 等客户签署多年协议实现收费运营；融资体量在数亿美元级别，但具体数值受口径影响，需谨慎解读。[10][50][52][56][57]

### 2.4 Apptronik（Apollo）

**技术路径与产品设计**

Apollo 是面向仓储、物流和制造的通用人形机器人，身高约 5 英尺 8 英寸、重量 160 磅，最大负载 55 磅，采用上半身与不同下肢配置的模块化设计，目标物料成本低于 5 万美元以支持量产与维护。[59]

Apptronik 与 Google DeepMind 合作，将 Apollo 作为 Gemini Robotics On-device 平台，在设备端执行低延迟推理，并声称通过 50–100 次演示即可适配新任务，体现“基础模型 + 示教学习”的技术路径。[59]

**商业合作与部署**

- 与 Mercedes-Benz 签署商业协议，在其工厂试点部署 Apollo，这是其首次公开商业部署，用于汽车制造场景。[60]  
- CNBC 报道 Apollo 已在 Mercedes-Benz、GXO 和 Jabil 的工厂或仓库指定区域执行搬运和分拣任务，当前依赖外部传感器与安全光幕划定安全区域，未来目标是实现协作安全。[61]  
- Analytics India Magazine 指出 Mercedes-Benz 使用遥操作技术远程控制 Apollo 完成任务，Apptronik 将这些遥操作数据与 Gemini Robotics 模型结合，用于训练和提升 Apollo 的自动能力，表明其采用“遥操作采数 + 基础模型训练”的闭环策略。[62]

**融资与估值**

- 2025 年 2 月：宣布 3.5 亿美元 A 轮融资，由 B Capital 和 Capital Factory 领投，Google 参投，用于迭代 Apollo、扩展制造能力和团队。[63][64]  
- 2026 年：CNBC 报道新增 5.2 亿美元融资（A 轮扩展），使整个 A 轮总额达 9.35 亿美元，对应公司估值约 50 亿美元。[61][65]

因此，Apptronik A 轮及其扩展轮总融资约 9.35 亿美元，估值约 50 亿美元，信息相对一致。[61][63][65]

**团队背景**

Apptronik 源自德州大学人本中心机器人实验室，团队曾参与 NASA Valkyrie 项目，2016 年分拆成立公司。[66] CEO Jeff Cardenas 拥有德州大学技术商业化硕士背景，创始团队成员在 NASA Johnson Space Center 参与 DARPA Robotics Challenge 项目。[67]

**小结**

Apollo 路线结合模块化硬件、与 Gemini Robotics 的深度合作以及遥操作采数训练策略，优势在于与传统制造企业深度对接；风险在于仍处指定区域试点，距完全协作生产线具有不确定性。[60][61][62][63]

### 2.5 Sanctuary AI（Phoenix）

**技术与产品路径**

Sanctuary 将 Phoenix 定位为“为工作设计的通用人形机器人”，强调工业级工作能力和接近人类的认知与运动水平。[68][69] 核心软件平台 Carbon 被描述为认知架构，整合现代 AI 技术，将自然语言翻译为动作，融合视觉、听觉与触觉实现感知、认知与任务规划，重点在于人手级灵巧性和眼手协调。[68][70]

其技术路线与多数人形公司不同：在其他公司优先攻克双足运动的背景下，Sanctuary 更强调嵌入式 AI、双臂操作与任务认知规划，目标是在工业场景中让 Phoenix 像人类一样理解和操控环境。[5][71]

在灵巧操作方面，Sanctuary 使用液压多指手、NVIDIA Isaac Lab 仿真和自研触觉传感器，展示零样本手内操作和复杂抓取装配任务，是工业强度灵巧操作的典型路径。[24]

**展会与部署**

- 2025 年汉诺威工业博览会上，Sanctuary 与微软联合展示 Phoenix，机器人在展会连续工作约 43.5 小时，展示连续操作能力。[72]  
- 公司博客展示 Phoenix 在零样本手内操作等任务中的表现，展示其 dexterous pipeline。[24][68]

**融资与团队**

- Robot Report 指出，Sanctuary 获得 BDC Thrive Venture Fund 和 InBC 等加拿大政府相关投资，截至 2024 年累计融资约 1.4 亿美元。[71][73]  
- Preqin 预览提到 2026 年 5 月 Zeon Ventures 追加投资，用于进一步开发 Phoenix 平台，目标行业包括汽车、制造和物流。[5]

团队由 Geordie Rose、Suzanne Gildert、Olivia Norton 和 Ajay Agrawal 于 2018 年在温哥华创立，成员来自量子计算公司 D-Wave、强化学习机器人公司 Kindred 和科学商业化孵化机构 Creative Destruction Lab。[74][75] 2024 年 CEO Geordie Rose 与 CTO Suzanne Gildert 离开，公司联合创始人 Olivia Norton 出任 CTO 和 CPO。[76]

**小结**

Sanctuary 在灵巧操作与认知架构方面具有差异化优势，融资体量中等（约 1.4 亿美元 + 2026 年新投资），当前商业化仍以试点与展会展示为主，离规模化工业部署尚有距离。[5][24][71]

### 2.6 1X Technologies（NEO）

**技术与产品路线**

1X 的 NEO 是面向家庭环境的柔体人形助理机器人，采用软材料和肌腱驱动提高安全性。[11] 公司提出 1X World Model，通过从互联网视频学习世界模型，将视觉理解转化为行动控制，利用人形硬件的相似动力学实现“从视频到动作”的迁移，定位家庭助理和陪伴。[11]

DroneXL 报道称，1X 在 2025 年 10 月开放 NEO 预购，价格约 2 万美元或 499 美元/月订阅，演示任务（如拿水、装洗碗机、叠衣服）均由佩戴 VR 头显的人类远程操作完成，机器人自主能力有限，执行速度较慢。[77] CEO 表示“没有用户数据就无法改进产品”，强调通过遥操作在家庭环境采集数据，并计划逐步由 AI 模型接管更多动作。[77][78]

Contrary Research 指出，1X 策略是在家庭环境部署 NEO，通过大规模遥操作采数训练具身 AI 模型，目标实现从人工控制到自主控制的过渡。[79]

**融资与团队**

1X（前身 Halodi Robotics）由 Bernt Øivind Børnich 于 2014 年创立，早期专注带轮人形 EVE 用于物流、安保和医疗，2022 年改名为 1X Technologies，转向家庭通用人形助手。[80] 融资包括 2023 年由 OpenAI Startup Fund 领投的 2350 万美元 A2 轮，2024 年由 EQT Ventures 领投的 1 亿美元 B 轮（Samsung NEXT 等参与），以及 2025 年寻求约 10 亿美元的后续融资计划。[80]

**小结**

1X 的差异化是“优先押注家庭场景 + 世界模型 + 大规模遥操作采数”；当前 NEO 商业化主要为预购与订阅，实际家庭任务高度依赖遥操作，短期更多是“数据工厂”而非完全自主产品。[11][77][79][80]

### 2.7 UBTECH（优必选：Walker 系列）

**技术与产品矩阵**

UBTECH 自 2012 年成立以来，推出 Alpha 教育与娱乐机器人以及多代 Walker 人形机器人，包括 Walker S 工业人形和 Walker C 服务型具身 AI 导览机器人。[81] Walker S2 是全尺寸工业人形，配备双电池热插拔、群脑网络 2.0 与 Co-Agent 双循环 AI 系统；Walker C 则作为具身 AI 导览员服务于 2025 大阪世博会中国馆，支持多语种讲解，在导览服务场景真实运营。[1][82]

**工业产能与订单**

- 21 世纪经济报道：Walker S 系列 2025 年工业人形年产能突破 1000 台，当年交付超过 500 台，计划 2026 年将产能提升至 1 万台，主要应用于汽车制造、智能制造、智慧物流与具身智能数据中心。[83]  
- PR Newswire：Walker S2 被称为“世界首批大规模交付的全尺寸工业人形之一”，自 2025 年初以来 Walker 系列累计订单超过 8 亿元人民币，计划 2025 年交付超过 500 台，2026、2027 年产能分别提升至 5000 台和 1 万台，客户包括 BYD、东风柳汽、吉利、FAW-Volkswagen、Audi FAW、BAIC、富士康、顺丰等。[84][85]

两类来源在产能与订单数据基本一致，显示 UBTECH 已形成较明确的工业级产品与订单积压。

**技术路线与团队**

UBTECH 强调仿真与真实工厂数据结合，认为现场光照变化等因素对视觉识别影响显著，需要大量真实工厂数据支撑算法迭代。[83] 路演资料显示，截至 2023 年底拥有授权专利超过 2100 件，发明专利占比超过 50%。[81] 创始人周剑担任董事会主席、执行董事与 CEO，具有自动化产业背景并在中国担任多项社会职务。[81][86]

**小结**

Walker S2 路线具有“国产工业人形 + 大订单 + 自有 BrainNet 平台”的特点，在中国汽车制造等领域形成较大规模试点与早期量产，从“进入工厂干实事”的角度处于全球前列；盈利能力与长期订单结构仍需时间验证。[83][84]

### 2.8 Unitree（宇树）

**技术与产品矩阵**

Unitree 由王兴兴于 2016 年在杭州创立，早期以四足机器人 Go1/Go2 等为主，2024 年起进入人形领域，强调“高性能 + 低成本”的工业设计理念。[87][88] 人形产品线包括：

- H1 / H1-2：全尺寸通用人形，身高约 180 cm、重量约 47 kg（H1），最高速度 3.3 m/s，配备 3D LiDAR 和深度相机实现 360° 感知，26 自由度，自研电机与减速器，被宣传为“中国首台能跑的全尺寸通用人形”，H1-2 在踝关节与手臂扭矩方面增强负载能力。[89][90]  
- G1：约 1.27 米高的中等身高人形，面向研究与教育市场，定价约 1.6 万美元，相比约 9 万美元的 H1 大幅降低成本，通过自研电机和减速器及减少线缆与螺丝实现高性价比。[91][92]  
- H2 / H2 Plus、R1：构成人形矩阵，H2 Plus 为 NVIDIA Isaac GR00T 的参考平台之一，说明 Unitree 在仿真与 AI 软件栈上与 NVIDIA 协同。[93][94]

**销量与商业化**

Gasgoo 报道 Unitree 在 2023–2025 年共销售超过 33,000 台四足机器人，全球市场份额居前，自 2024 年起人形产品线（G1、R1、H2）快速拉升营收，公司通过消费级 Go 系列与工业 B 系列共享技术摊薄成本。[95] Unitree 官方商城博客对市场上夸大的销量做出澄清，给出 2025 年人形机器人实际发货量超过 5,500 台，指代已销售并交付数量。[96]

综合可认定：

- 2023–2025 年四足机器人累计销量约 3.3 万台；  
- 2025 年人形机器人实际发货量 > 5,500 台；  
- 人形线自 2024 年起成为公司营收重要增量。[95][96]

**团队与资本市场**

王兴兴具机电与工程背景，自 2016 年起担任 Unitree CEO/CTO。[87][97] Gasgoo 报道 Unitree 已通过科创板 IPO 审核，使其成为少数即将或已经进入资本市场的人形/四足机器人公司之一。[95]

**小结**

Unitree 优势在于高性能低成本硬件、大规模四足销量积累及与 NVIDIA GR00T 的生态合作，人形业务在 2025 年已实现显著出货，当前主要面向研发、教育与部分工业评估市场，工业场景的深度试点仍在推进中。[90][93][95][96]

### 2.9 Fourier Intelligence、小米等（简要）

- **傅利叶智能**：截至 2025 年初累计融资超过 16 亿元人民币，其中 2025 年 1 月 E 轮近 8 亿元，5 月润阳科技战略投资 3 亿元，之前 2022 年 D 轮 4 亿元，由软银愿景基金等投资。[98][99] 36 氪 Pitchhub 指出其核心团队具 FANUC 与 GM 泛亚等背景，产品线涵盖康复机器人与 N1 开源人形平台。[98]  
- **小米机器人团队**：在 CyberOne 全尺寸人形仿生机器人基础上迭代发展，根据机构调研和博客，小米在 2025 年 2 月公布最新进展，强调与智能家居生态结合；图谱未包含足够技术与商用细节，本报告不做展开，仅作为背景提及。[100][101][102]

---

## 第三章 机器人基础模型 / VLA 路线及关键玩家

### 3.1 Google DeepMind – Gemini Robotics

Gemini Robotics 基于 Gemini 2.0，将物理动作作为新输出模态直接控制机器人，目标大幅提升通用性、交互性与灵巧性。[13][14] 技术报告宣称该系统在综合具身任务基准上的表现是其他先进 VLA 的两倍以上，ER 1.5/1.6 版本通过 Gemini API 向开发者开放具身推理能力，在多个具身基准上优于此前 VLA 和通用 Gemini 3.0 Flash。[14]

部署形态以云端基础模型 + API 为主，配合传统控制器形成双层架构。Google DeepMind 与 Boston Dynamics 的合作将 Gemini Robotics 集成到新一代电动 Atlas 中，辅以 Orbit 软件平台实现与工厂系统集成，体现“模型 + 工业硬件 + 软件平台”的路线。[3][103][104]

### 3.2 NVIDIA – Project GR00T

Project GR00T 以 GR00T N1/N1.5 基础模型为核心，目标理解自然语言、学习人类示范动作并实现协调与灵巧行为。[15] 其平台通过 Jetson Thor 硬件与 Isaac Sim/Lab 仿真提供从数据合成、训练到部署的完整流水线。[1][15]

2025 年，GR00T N1.5 借助 GR00T-Dreams 生成合成运动数据，在约 36 小时内完成训练，专注物料搬运和排序等工业任务泛化，多家人形与机械臂厂商（如 Agility、Boston Dynamics、Unitree）采用 Isaac/GR00T 作为 AI 平台。[15][93][94]

### 3.3 Physical Intelligence – π 系列

Physical Intelligence 2024 年发布 π0，定位通用机器人基础模型，以图像+文本输入、底层电机命令输出，支持多种机器人形态。[16] 后续 π0.5、π*0.6、π0.7 引入 RL 与记忆模块并开源权重和代码，构建“Physical Intelligence Layer”，通过模型授权或 SaaS 商业化。[16]

路线特点是：直接控制电机层、侧重多机器人多任务数据与 RL，服务工业和服务场景，为硬件方提供统一策略层。

### 3.4 Figure – Helix VLA

Helix 为 Figure 的通用 VLA 模型，将感知、语言理解和控制整合为单一网络，输入视频与语言，输出全身控制信号。通过真实与仿真数据联合训练，支持多机器人协作和未见物体抓取，并在嵌入式 GPU 上高频运行。[17][29]

Helix 已在 Figure 02/03 上完成家务和物流任务的控制，与 BotQ 工厂和工厂任务数据闭环结合，构成“互联网规模预训练 + 工厂任务 RL + 家庭演示数据”的综合数据路径。[28][29][34]

### 3.5 开源 VLA：OpenVLA / Open X-Embodiment / RT-X

OpenVLA 为 7B 参数开源 VLA 模型，基于 Open X-Embodiment 数据集约 97 万段机器人经验预训练，支持多种机器人开箱即用，并提供完整训练与推理流水线。[18] Open X-Embodiment/RT-X 提供目前最大公开机器人数据集和 RT-X 系列模型，实验表明跨机器人预训练（RT-1-X、RT-2-X 等）带来正迁移性能提升。[18]

这一开源路线对学术与初创公司影响显著，为行业提供基线模型和数据标准。

### 3.6 Amazon Robotics 与 Meta 等内生基础模型

- **Amazon Robotics**：外部报道指出，亚马逊内部构建了面向仓储移动机器人车队的 DeepFleet 基础模型，用于路径规划和调度，是“车队级基础模型”，但公开信息尚不足以证实其具身 VLA 的具体规模与接口。[1]  
- **Meta**：通过 Habitat 3.0 仿真、Sparsh 触觉与 dexterity 数据集、PARTNR 基准等，构建具身 AI 基础设施，重点在仿真与评测；尚未公开类似 Gemini Robotics 或 π 系列那样统一的 VLA 基础模型细节。[1]

### 3.7 综合观察

综合上述玩家：

- 机器人基础模型与 VLA 正演化为具身智能的“平台层”：一类通过云端 API 服务多种机器人（Gemini Robotics、GR00T N1.5），一类与特定硬件深度耦合（Helix、1X World Model、π 系列）。[13][16][17]  
- 世界模型与视频预训练成为主流趋势，架构从单层 VLA 向“世界模型 + 控制/VLA”两层结构演进。[19]  
- 优势玩家往往在硬件、基础模型和仿真平台三方面同时建立能力，如 Boston Dynamics + Gemini、Agility + GR00T、Figure + Helix + BotQ、UBTECH Walker S2 + BrainNet/Co-Agent。[1][3][15][84][105]

---

## 第四章 轮式移动操作与仓储物流路线

图谱对 Locus、Geek+、Mujin、Dexterity、RightHand、Exotec、Hai Robotics、Amazon Robotics 等企业的资料尚不完整，以下结合已收录的 Digit 与 Stretch 等案例和技术路线进行较高层次的梳理。

### 4.1 技术路线与形态分类

轮式移动操作 / 仓储机器人主要形态包括：[1][20]

1. 纯 AMR：仅搬运货架或托盘，如传统货到人系统。  
2. AMR + 机械臂移动操作：AMR 搭载机械臂执行取放，如 Locus Array、Dexterity 平台等。  
3. 箱式 ACR / Skypod 立体仓：如 Hai Robotics 的 ACR 系统、Exotec 的 Skypod，使用专用立体存储和提升机制。  
4. 龙门 + 输送 / ASRS：如 Cimcorp 和 Swisslog 的龙门机器人与自动存取系统。  
5. Dock 自动化与集装箱装卸：Dexterity DexR、Berkshire Grey Scoop 等，面向卡车 / 集装箱装卸场景。  
6. 远程操作 + 自主融合：Dexterity 明确采用自动模式 + 远程监控/干预策略。  

这些路线在技术上均依赖 AMR 底盘、机械臂和末端执行器，以及导航、视觉、抓取与调度算法，差异主要体现在系统结构和任务定位上。

### 4.2 Digit：人形形态的移动操作

Digit 虽归类为人形机器人，但在仓储环境中扮演典型移动操作平台角色：[21][50]

- 在仓库执行 tote 搬运与取放任务，与 AMR 和输送线协作。  
- 通过 Agility Arc 云平台监控车队级运行指标，与 WMS/WES 集成。  

Digit 在 GXO 的 RaaS 部署被视为具身智能领域最早的商业化移动操作案例之一，表明移动操作在物流场景的可行性与经济性。[10][20][54]

### 4.3 Stretch：研究与初创标准平台

Hello Robot Stretch 4 是九自由度移动操作平台，采用三轮全向底盘、升降与伸缩臂、3D 视觉及嵌入式计算平台。[22] Stretch AI 作为开源具身 AI 框架，支持 open-vocabulary 移动操作和示教学习，社区已有使用 LLM/VLM 实现任意物体识别及协调底座与机械臂执行取放的示例。[22]

材料显示 Stretch 在学术界和初创中被广泛采用，是移动操作研究和原型验证的事实标准平台之一。[22]

### 4.4 轮式移动操作路线整体评估

结合 Digit 与 Stretch 案例及路线综述可得：

- 商业成熟度方面，轮式 / 轮足移动操作在仓储和服务等平面场景已进入“成熟商用 + 向具身基础模型升级”阶段，是具身智能领域最早实现稳定盈利的方向之一。[1][20]  
- 技术演进路径是从脚本/行为树控制向引入 open-vocabulary 与 VLA 的语义感知控制过渡，具身基础模型逐步渗透仓储拣选、移动取放任务。[1][20][22]  
- 平台角色方面，Digit 和 Stretch 分别作为工业标杆和研究标准平台，为传统物流自动化向具身智能过渡提供了关键实验平台和商业样本。[21][22][50][54]

需指出的是：图谱中尚缺 Geek+、Locus、Mujin、Dexterity、RightHand、Exotec、Hai Robotics、Amazon Robotics 等公司在技术路径、商业化规模、融资与团队上的完整信息，对“全球仓储 AMR/移动操作格局”的定量比较仍存明显缺口。

---

## 第五章 灵巧操作与末端执行器路线

### 5.1 硬件、软件与全栈路径

灵巧操作需要多指高自由度机械手、复杂驱动与高带宽力触觉传感，配合端到端 AI 模型及仿真到现实技术应对非结构化接触和变形物体。[23] 当前市场可按切入点划分为：

- 硬件导向：专注灵巧手与夹爪等末端执行器，后续与用户或软件伙伴配合控制策略。  
- 软件 / 模型导向：强调 VLA、RL、世界模型及仿真工具，依赖标准机械手。  
- 全栈公司：同时掌握机械手硬件、仿真平台、AI 模型与部署方案，将灵巧操作嵌入完整机器人系统。

在图谱中，最典型的全栈玩家是 Sanctuary 和 Figure。[1][24][25]

### 5.2 Sanctuary：液压多指手 + Carbon + Isaac Lab

Sanctuary 构建液压多指手与自研触觉传感器，并利用 NVIDIA Isaac Lab 进行 dexterous learning，加速仿真训练并迁移到现实。其 Carbon 认知架构将自然语言翻译为动作，融合视觉、听觉和触觉实现感知、认知和任务规划，使 Phoenix 能执行复杂抓取与装配任务。[24][68][70]

这一路线代表“工业强度灵巧操作”：硬件使用高性能液压手，软件采用多模态认知 + RL + 仿真 pipeline，面向工厂和物流等场景的高复杂度任务。[24][68][71]

### 5.3 Figure：Helix-02 下的全身协作

Figure 在 Helix-02 驱动下，让两台人形在卧室环境协同完成开门、搬动家具、挂衣和整理床铺等任务，特别是床铺整理涉及对大面积可变形物体的协调操作。[25] 两台机器人通过各自视觉观察对方运动推断意图，无中央规划器或显式通信，使用单一神经网络策略完成多机器人全身协作任务。[25]

这一案例展示了“灵巧操作 + 全身协调 + 多机器人协作”的综合能力，是人形机器人进入家庭复杂家务的重要技术示例。

### 5.4 阶段性结论

- 灵巧操作仍以研究与早期工业试点为主，尚未广泛商业化。[23]  
- 高性能机械手、高保真仿真和多模态基础模型是构建灵巧操作 pipeline 的三大支柱，是进入家庭复杂家务与高端工业装配场景的关键门槛。[23][24][25]  
- Sanctuary 与 Figure 分别从工业强度和家用协作角度提供了标杆案例，对后续产品化具有重要参考意义。

---

## 第六章 综合比较与趋势研判

### 6.1 技术集成度：硬件 + 模型 + 仿真

行业经验显示，仅依靠硬件或模型难以在通用机器人竞争中保持优势。未来领先者往往在硬件、基础模型和仿真平台三方面同时构建能力：[1][105]

- Boston Dynamics + Gemini：Atlas 整合 Gemini Robotics 基础模型，辅以 Orbit 软件平台接入工厂系统，形成“硬件 + 模型 + 软件平台”的方案。[3][104]  
- Agility Digit + GR00T：Digit 与 NVIDIA Isaac/GR00T 生态结合，利用仿真与基础模型支持工业任务泛化。[15][21]  
- Figure 03 + Helix + BotQ：结合人形硬件、Helix VLA 与自建 BotQ 工厂，构成端到端体系。[28][29]  
- UBTECH Walker S2 + BrainNet/Co-Agent：以脑网平台支持场景配置、快速部署与多机协同。[84][85]

技术集成度本身正在成为竞争优势，单一环节玩家可能被“硬件 + 模型 + 仿真”生态中的平台公司边缘化。

### 6.2 数据与世界模型

Gemini Robotics、GR00T-Dreams、1X World Model 等系统均强调通过视频理解物理世界支撑下游控制。[1][14][15][11][19]

- 数据来源包括人/机器人示教、跨机器人数据集（Open X-Embodiment/RT-X）、仿真与世界模型生成的合成数据，以及家庭与工厂场景的大规模遥操作采集数据（如 1X 与 Apptronik）。[1][16][18][62][79]  
- 架构逐步演化为“世界模型 + 控制/VLA”的两层结构，提高物理理解能力与跨任务泛化能力。[19]

对投资者而言，掌握高质量多模态数据及其世界模型能力是评估具身智能公司长期护城河的重要维度。

### 6.3 商业模式：整机销售 vs RaaS vs SaaS

当前商业模式呈现多样化：

- **整机销售**：  
  - Unitree H1/G1/H2 面向研发、教育和部分工业客户，以硬件销售为主。[90][91]  
  - UBTECH Walker S2 通过整机销售和大订单进入汽车与智能工厂场景。[84][85]

- **RaaS（Robots-as-a-Service）**：  
  - Agility Digit 在 GXO 的 RaaS 部署按人类工时约 30 美元/小时收费，目标两年内帮助客户回本。[54]  
  - Figure 与部分早期客户、Apptronik 在部分工厂案例中也采用按服务计费或“机器人 + 服务”的组合模式。[34][61]

- **SaaS / 模型授权**：  
  - Physical Intelligence 提供 π 系列模型授权或 SaaS，作为“物理智能层”，支持多机器人、多任务。[16]  
  - Gemini Robotics 与 GR00T 的 API 也可视为模型层 SaaS，通过云端 API 或 On-device 授权构建商业模式。[14][15]

各模式对应不同的现金流与风险结构：整机销售落地快但需重资本制造能力；RaaS 平滑客户 CAPEX 但对运营与运维能力要求高；SaaS/模型授权资本效率高但依赖广泛硬件合作生态。

### 6.4 资本投入与团队背景

资本层面，人形与基础模型方向已吸引百亿级美元资金：

- Figure：B+C 轮合计超过 16.75 亿美元，对应 26 亿与 390 亿美元估值，投资方涵盖 Microsoft、OpenAI Startup Fund、NVIDIA、Intel、Qualcomm Ventures 等。[35][37][38]  
- Apptronik：A 轮及扩展轮约 9.35 亿美元，对应 50 亿美元估值。[61][63][65]  
- Sanctuary：截至 2024 年累计融资约 1.4 亿美元，2026 年获 Zeon Ventures 新投资。[5][71]  
- 1X：A2+B 轮约 1.235 亿美元，另有约 10 亿美元融资意向。[80]  
- 中国厂商：UBTECH、Unitree、傅利叶等通过 IPO 或多轮融资取得数十亿人民币级资金。[84][95][98]

团队背景上，许多公司由具备顶级科研或创业背景的团队创立：  
- Figure：连续创业者 + 航空工程背景；[39]  
- Sanctuary：D-Wave/Kindred/CDL 背景；[74][75]  
- Apptronik：NASA Valkyrie 项目团队；[66][67]  
- Unitree：工程导向的“高性能 + 低成本”团队；[87][97]  
- UBTECH：在教育与服务机器人领域长期积累。[81]

### 6.5 关键不确定性

综合分析，当前具身智能领域存在以下关键不确定性：

1. **规模化部署速度**  
   Figure-BMW 案例表明，从单机试点到多机器人车队端到端运营存在较长过渡期；UBTECH、Unitree 等公布的产能与订单规划有待长期交付纪录验证。[30][31][32][33][83][84]

2. **财务可持续性与盈利模式**  
   高 CapEx 的人形与移动操作项目需通过 RaaS 或多年合同回收，大量前期投资能否转化为持续现金流仍待观察。[54][61]

3. **技术路径收敛与标准化**  
   世界模型 + VLA 双层架构仍在演化，不同公司接口与数据标准是否能形成行业共识尚不明确。

4. **监管与安全**  
   多数人形与移动操作部署仍依赖安全光幕等硬隔离，真正与人协作的协作安全标准与法规仍在形成。

---

## 局限与后续观察方向

1. **公司与路线覆盖局限**  
   图谱对 Geek+、Locus、Mujin、Dexterity、RightHand、Exotec、Hai Robotics、Amazon Robotics 等仓储与移动操作公司存在丰富来源，但未完全抽取为结构化证据，因此本报告未对这些企业逐一展开，属于对仓储/轮式路线覆盖的不足。[1]

2. **数据口径差异与区间表述**  
   - Agility 融资总额在 Startup Intros 与 TSG Invest 间存在显著差异（约 2.88 亿 vs 约 6.4 亿美元），本报告采用区间和多源并列方式呈现，不对具体数字作单一判断。[6][56][57]  
   - Figure-BMW 部署规模在 Figure 官方、BMW 官方和第三方媒体之间存在明显表述差异，本报告明确指出 Figure 宣称“参与生产 30,000 辆车”，BMW 将其定性为“试点”，Fortune 认为截至 2025 年 3 月仅一台机器人主要在夜班练习，并据此将项目定位为“高强度单机试点”，避免过度夸大。[30][31][32][33]

3. **商业化阶段与收入数据缺失**  
   多数公司未公开具体收入规模，特别是 Tesla Optimus 尚未产生显著收入，Digit 与 Apollo 的 RaaS 收入也主要通过定性描述体现，报告仅对“是否产生收入、是否有付费客户”做定性判断，不对收入规模作推测。[47][54][61]

4. **技术细节与模型参数不充分**  
   对 Gemini Robotics、GR00T、π 系列等基础模型的参数规模与训练数据构成，现有资料多为定性描述，报告仅在已公开信息下总结架构与功能特点，不添加未公开细节。[14][15][16]

5. **后续观察方向**  
   - 人形机器人在汽车与 3C 工厂中多机器人车队部署进展（Figure、Apptronik、UBTECH、Unitree 等）。  
   - 世界模型与视频预训练在工业与家庭场景中的实际效果，以及开源与闭源生态的演化。  
   - RaaS 与整机销售模式在不同地区与行业的经济性和客户接受度，尤其是运维与安全责任分配。  
   - 灵巧操作在高端装配和家庭场景中的真实部署案例，以验证当前 pipeline 的技术成熟度与成本结构。[23][24][25]

---

## 参考文献

[1] Open X-Embodiment: Robotic Learning Datasets and RT-X Models https://robotics-transformer-x.github.io/

[2] google-deepmind/open_x_embodiment https://github.com/google-deepmind/open_x_embodiment

[3] Scaling up learning across many different robot types https://deepmind.google/blog/scaling-up-learning-across-many-different-robot-types/

[4] Gemini Robotics brings AI into the physical world https://deepmind.google/blog/gemini-robotics-brings-ai-into-the-physical-world/

[5] Gemini Robotics - Google DeepMind https://deepmind.google/models/gemini-robotics

[6] Gemini Robotics 1.5 brings AI agents into the physical world https://deepmind.google/blog/gemini-robotics-15-brings-ai-agents-into-the-physical-world

[7] Agile Robots and Google DeepMind partner to bring intelligence to robotics https://www.agile-robots.com/en/news/detail/agile-robots-and-google-deepmind-partner-to-bring-intelligence-to-robotics/

[8] Physical Intelligence (π) 官方主页 https://www.pi.website/

[9] π0: Our First Generalist Policy https://www.pi.website/blog/pi0

[10] Physical Intelligence (π) – Blog https://www.pi.website/blog

[11] Physical Intelligence open sources Pi0 robotics foundation model https://www.therobotreport.com/physical-intelligence-open-sources-pi0-robotics-foundation-model

[12] Physical Intelligence – Enhanced Profile https://siliconvalleyinvestclub.com/physical-intelligence

[13] The Future of Robotics: Robotics Foundation Models and the role of data https://covariant.ai/insights/the-future-of-robotics-robotics-foundation-models-and-the-role-of-data/

[14] Amazon hires from AI robotics startup Covariant, licenses technology https://www.aboutamazon.com/news/company-news/amazon-covariant-ai-robots

[15] Amazon hires the founders of robotics AI startup Covariant https://techcrunch.com/2024/08/31/amazon-hires-the-founders-of-robotics-ai-startup-covariant

[16] Bringing robots from lab to the real world https://covariant.ai/insights/bringing-robots-from-lab-to-the-real-world/

[17] Announcing our $300M Series A Funding https://www.skild.ai/blogs/announcing-our-300m-series-a

[18] Skild AI funding, news & analysis https://sacra.com/c/skild-ai

[19] Skild AI Announces $300M Series A Funding https://humanoidroboticstechnology.com/industry-news/skild-ai-announces-300m-series-a-funding

[20] Building the general-purpose robotic brain https://www.skild.ai/blogs/building-the-general-purpose-robotic-brain

[21] NVIDIA Announces Project GR00T Foundation Model for Humanoid Robots https://nvidianews.nvidia.com/news/foundation-model-isaac-robotics-platform

[22] NVIDIA Isaac GR00T N1 is an open generalist foundation model for humanoid robots https://www.facebook.com/NVIDIARobotics/posts/nvidia-isaac-gr00t-n1-is-an-open-generalist-foundation-model-for-humanoidrobots-/1136201551883878/

[23] Isaac GR00T - Generalist Robot 00 Technology https://developer.nvidia.com/isaac/gr00t

[24] Advancing embodied AI through progress in touch perception, robot dexterity, and HRI https://ai.meta.com/blog/fair-robotics-open-source/

[25] Habitat 3.0: A Co-Habitat for Humans, Avatars and Robots https://ai.meta.com/research/publications/habitat-3-0-a-co-habitat-for-humans-avatars-and-robots/

[26] AI at Meta: Meta AI Products, Models and Research https://ai.meta.com/

[27] ANYbotics Raises Additional $60 Million to Drive U.S. Expansion https://www.anybotics.com/news/anybotics-raises-additional-60-million-to-drive-u-s-expansion/

[28] About the company - ANYbotics https://www.anybotics.com/about-us/

[29] We are Agile Robots | Driving industries forward | Agile Robots SE https://www.agile-robots.com/en/

[30] Figure AI – Official Website https://www.figure.ai/

[31] Figure AI - Wikipedia https://en.wikipedia.org/wiki/Figure_AI

[32] Figure raises $675M and signs collaboration agreement with OpenAI https://metrology.news/figure-raises-675m-and-signs-collaboration-agreement-with-openai/

[33] Brett Adcock on ending Figure’s collaboration with OpenAI https://x.com/adcock_brett/status/1886860098980733197

[34] Figure Exceeds $1B in Series C Funding at $39B Post-Money Valuation https://www.figure.ai/news/series-c

[35] 1X | Home Robots https://www.1x.tech/

[36] Locus Robotics launches Locus Array for fully autonomous fulfillment https://www.therobotreport.com/locus-robotics-launches-locus-array-for-fully-autonomous-fulfillment

[37] Locus Array - Locus Robotics https://locusrobotics.com/locusone/fleet/locus-array

[38] Locus Robotics: Acquisition Of Nexera Robotics Advances Autonomous Warehouse Fulfillment（页面为 News 集合） https://locusrobotics.com/news

[39] How Much Did Locus Robotics Raise? Funding & Key Investors | Clay https://www.clay.com/dossier/locus-robotics-funding

[40] Locus Robotics Surpasses 5 Billion Pick Milestone, Accelerating Global Adoption of Mobile Warehouse Automation https://www.prnewswire.com/news-releases/locus-robotics-surpasses-5-billion-pick-milestone-accelerating-global-adoption-of-mobile-warehouse-automation-302436658.html

[41] Automation integrator - Cimcorp https://cimcorp.com

[42] Robotics and software - Cimcorp https://cimcorp.com/warehouse-and-distribution/products-and-solutions/robotics-and-software

[43] CeMAT: Cimcorp to showcase robotic order fulfillment technology with the potential to double sales through shorter lead times https://cimcorp.com/general/cemat-cimcorp-to-showcase-robotic-order-fulfillment-technology-with-the-potential-to-double-sales-through-shorter-lead-times

[44] Cimcorp releases 50-year anniversary movie https://cimcorp.com/general/future-of-automation-movie

[45] Geekplus Announces 2025 Interim Results: Revenue and Profit Soar https://www.geekplus.com/resources/news/ipo-interim-results

[46] Geekplus Lists on HKEX, Revolutionizing Global Logistics with Robotics https://www.geekplus.com/resources/news/geekplus-lists-on-hkex-main-board-pioneering-the-global-smart-logistics-transformation-with-robotics

[47] Geekplus | Company News ▪ Industry Study | IPO https://www.geekplus.com/resources/news/tag/ipo

[48] Geekplus HK$2.71 billion IPO and HKEX listing https://www.davispolk.com/experience/geekplus-hk-2-71-billion-ipo-and-hkex-listing

[49] Rise Of The Robots—Geek+ Raises $100M At $2B Valuation https://news.crunchbase.com/ai-robotics/geek-raises-startup-warehousing/

[50] Mujin Raises US$ 233 Million to Accelerate Global Growth and Drive the Future of Intelligent Automation https://mujin-corp.com/resources/news/seriesd-announcement-advancing-industrial-automation-intelligent-robotics

[51] Mujin secures $233M in Series D funding round https://www.robotics247.com/article/mujin_secures_233m_in_series_d_funding_round

[52] Mujin Raises $233M in Funding for Global Expansion of MujinOS（LinkedIn 帖子） https://www.linkedin.com/posts/mujin-corp_mujin-mujinos-industrialautomation-activity-7401621511763181570-TK1Y

[53] Mujin $233 Million funding round 2025-12-02 https://app.fundz.net/fundings/mujin-funding-round-series-d-9f4317

[54] Mujin Raises US$ 233 Million to Accelerate Global Growth and Drive the Future of Intelligent Automation https://japanstartupobserver.substack.com/p/mujin-raises-us-233-million-to-accelerate

[55] Dexterity picks up $95M in funding for container loading robots https://www.therobotreport.com/dexterity-picks-up-95m-funding-container-unloading-robots

[56] Dexterity raises $95M to accelerate Physical AI | Dexterity, Inc. posted on the topic | LinkedIn https://www.linkedin.com/posts/dexterityinc_physicalai-robotics-innovation-activity-7305301173199069184-mlGk

[57] 🚨 BREAKING: Dexterity, Inc. has secured $95 million in new funding to advance its "Physical AI" development.（Lukas M. Ziegler 帖子） https://www.linkedin.com/posts/zieglerr_breaking-dexterity-inc-has-secured-activity-7306244207453638727-cGiV

[58] Berkshire Grey https://www.berkshiregrey.com/

[59] Berkshire Grey Press Releases https://www.berkshiregrey.com/resources/press-release/

[60] Berkshire Grey Enters into Definitive Merger Agreement with SoftBank Group Corp. for Go-Private Transaction https://www.berkshiregrey.com/resources/press-release/berkshire-grey-enters-into-definitive-merger-agreement-with-softbank-group-for-go-private-transaction/

[61] RightHand Robotics, Inc. Secures New Funding as Yaro Tenzer is Appointed CEO https://righthandrobotics.com/the-latest/righthand-robotics-inc-secures-new-funding-as-yaro-tenzer-is-appointed-ceo-2

[62] RightHand Robotics Secures $66 Million in Series C Funding https://righthandrobotics.com/the-latest/righthand-robotics-secures-66-million-in-series-c-funding

[63] RightHand Robotics Funding Rounds & Investor Information https://exa.ai/websets/directory/righthand-robotics-funding

[64] Mobile Industrial Robots - Automate your internal transportation https://mobile-industrial-robots.com/

[65] Autonomous Mobile Robots - Discover AMRs from MiR https://mobile-industrial-robots.com/products/robots

[66] Universal Robots and Mobile Industrial Robots to Debut New and AI Powered Automation Solutions Across Integrated Industry Workflows at Automate 2025 https://www.universal-robots.com/news-and-media/news-center/universal-robots-and-mobile-industrial-robots-to-debut-new-and-ai-powered-automation-solutions-across-integrated-industry-workflows-at-automate-2025/

[67] Amazon robotics: Meet the robots inside fulfillment centers https://www.aboutamazon.com/news/operations/amazon-robotics-robots-fulfillment-center

[68] Robotics | Research Areas - Amazon Science https://www.amazon.science/research-areas/robotics

[69] Amazon announces over €700 million investment in robotics and AI powered technologies across Europe https://www.aboutamazon.eu/news/innovation/amazon-announces-over-700-million-investment-in-robotics-and-ai-powered-technologies-across-europe

[70] Brett Adcock Bio https://www.brettadcock.com/bio

[71] Helix: A Vision-Language-Action Model for Generalist Humanoid Control https://www.figure.ai/news/helix

[72] Figure AI - News https://www.figure.ai/news

[73] F.02 Contributed to the Production of 30,000 Cars at BMW https://www.figure.ai/news/production-at-bmw

[74] Humanoid robots at BMW plants https://www.bmwgroup.com/en/news/general/2026/humanoid-robot-in-leipzig.html

[75] Figure AI passes $1B with Series C funding toward humanoid robot development https://www.therobotreport.com/figure-ai-raises-1b-in-series-c-funding-toward-humanoid-robot-development

[76] Figure Raises $675M at $2.6B Valuation and Signs Collaboration Agreement with OpenAI https://www.prnewswire.com/news-releases/figure-raises-675m-at-2-6b-valuation-and-signs-collaboration-agreement-with-openai-302074897.html

[77] Figure Exceeds $1B in Series C Funding at $39B Post-Money Valuation (PR Newswire) https://www.prnewswire.com/news-releases/figure-exceeds-1b-in-series-c-funding-at-39b-post-money-valuation-302556936.html

[78] Tesla AI https://www.tesla.com/AI

[79] Optimus (robot) - Wikipedia https://en.wikipedia.org/wiki/Optimus_(robot)

[80] Tesla to have humanoid robots for internal use next year, Musk says https://www.reuters.com/business/autos-transportation/tesla-have-humanoid-robots-internal-use-next-year-musk-says-2024-07-22/

[81] Tesla’s Optimus Robot: Uses and Release Timeline https://builtin.com/robotics/tesla-robot

[82] Tesla Inc. 2025 Form 10-K https://www.sec.gov/Archives/edgar/data/1318605/000162828026003952/tsla-20251231.htm

[83] Tesla’s Optimus Robots Were Remotely Operated at Cybercab Event https://www.bloomberg.com/news/articles/2024-10-14/tesla-s-optimus-robots-were-remotely-operated-at-cybercab-event

[84] Agility Robotics - Company https://www.agilityrobotics.com/company

[85] Agility Robotics Stock: $2.1B Valuation — Is It a Buy? https://tsginvest.com/agility-robotics/

[86] Agility Robotics - Digit Product Page https://www.agilityrobotics.com/

[87] Agility Robotics to open factory for humanoid robots in Oregon https://www.statesmanjournal.com/story/money/business/2023/09/19/agility-robotics-opening-robofab-humanoid-robot-digit-factory-salem-oregon/70900714007

[88] Agility Robotics' Digit humanoids land first official job https://www.therobotreport.com/agility-robotics-digit-humanoid-lands-first-official-job

[89] Agility Robotics - StartupIntros profile https://startupintros.com/orgs/agility-robotics

[90] Apptronik - Leadership https://apptronik.com/leadership

[91] Apptronik Co-Founder Jeff Cardenas is Building Humanoid Robots https://news.mccombs.utexas.edu/magazine/2024-spring-summer/year-of-ai-ai-in-action

[92] Sacra Apptronik Company Research https://sacra.com/c/apptronik

[93] Apptronik - Press Releases https://apptronik.com/press-release

[94] Analytics India Magazine LinkedIn post on Apptronik funding and teleoperation https://www.linkedin.com/posts/analytics-india-magazine_apptronik-has-raised-an-additional-53-million-activity-7307996259007533056-n-RX

[95] Apptronik raises $520M to beat Chinese humanoids, Tesla Optimus to market https://www.cnbc.com/2026/02/11/apptronik-raises-520-million-at-5-billion-valuation-for-apollo-robot.html

[96] Apptronik and Mercedes-Benz Enter Commercial Agreement https://apptronik.com/news-collection/apptronik-and-mercedes-benz-enter-commercial-agreement

[97] 1X Technologies - Wikipedia https://en.wikipedia.org/wiki/1X_Technologies

[98] 1X Business Breakdown & Founding Story - Contrary Research https://research.contrary.com/company/1x

[99] 1X’s $20,000 NEO Humanoid Robot Launches With A Catch: It Needs Humans To Do Your Chores https://dronexl.co/2025/10/29/1xs-neo-humanoid-robot-launches-chores

[100] Sanctuary AI - Saltagen Ventures Portfolio https://www.saltagen.com/portfolio/sanctuary-ai

[101] Sanctuary AI entry - KÜRE Ansiklopedi https://kureansiklopedi.com/tr/detay/sanctuary-ai-02316

[102] Sanctuary AI company profile - nextomoro https://nextomoro.com/sanctuary-ai/

[103] Sanctuary AI Unveils Phoenix™ - A Humanoid General-Purpose Robot Designed for Work https://www.sanctuary.ai/blog/sanctuary-ai-unveils-phoenix-a-humanoid-general-purpose-robot-designed-for-work

[104] Sanctuary AI - Preqin profile (preview) https://www.preqin.com/data/profile/asset/sanctuary-ai/445532

[105] Sanctuary AI obtains Canadian funding for general-purpose humanoid development https://www.therobotreport.com/sanctuary-ai-obtains-canadian-funding-general-purpose-humanoid-development
