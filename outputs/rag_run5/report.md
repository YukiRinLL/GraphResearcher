## 摘要

具身智能在近年出现两条相互促进的技术主线：其一是以视觉-语言-动作（VLA）/具身多模态模型为代表的“从互联网知识到机器人控制”的端到端策略学习与泛化路线，代表性工作包括 RT-1（面向真实世界规模化控制的 Robotics Transformer）与 RT-2（Vision-Language-Action Models，将 web knowledge 迁移到机器人控制，并将互联网规模视觉-语言模型能力并入端到端控制以提升泛化）[1][2][3][4][5]，以及具身多模态语言模型 PaLM-E[6]与语言—可供性对齐的 SayCan[7]。其二是以生成式方法与数据工程为抓手，强化策略学习的可扩展性与可落地性：动作扩散（Action Diffusion）用于视觉-运动策略学习（2023-03-07 发布）[8]，并存在开源实现入口 Diffusion Policy[9]；面向双臂移动操作的低成本全身遥操作数据采集（Mobile ALOHA，2024-01-04）为“可规模采集的高质量示教数据”提供了方法学样例[10]；在数据层面，BridgeData V2 作为“robot learning at scale”的数据集论文入口提供了可引用锚点[11]；在仿真层面，MuJoCo 于 2022-05-23 开源，为仿真与工具链生态演进提供了关键节点[12]。

在产业端，本报告选取具备公开证据的代表主体进行对比：Boston Dynamics 宣布退役液压 Atlas 并发布全电驱 Atlas，强调“更强壮、更大运动范围”并探索多种夹爪以适配客户环境操作需求；其试点/商业化路径表述为从 Hyundai 开始，并先与小范围创新客户迭代应用[13]。Apptronik 在 2026-02-11 披露获得 5.2 亿美元融资，投资方包括 Mercedes-Benz、John Deere、Qatar Investment Authority；并被报道宣布与制造/供应链公司 Jabil 建立新的试点合作伙伴关系[14][15]。Fourier Intelligence 的 GR-1 官方资料出现“Powered by LLM”表述，并提到 Smart Actuator（FSA）将电机/驱动/减速器/编码器集成为单一模块以提供动力与控制[16][17]。平台侧，NVIDIA 在 2024-03-18 宣布面向人形机器人的 Project GR00T foundation model，并更新 Isaac Robotics 平台；在 2025-03-18 新闻稿中宣布 Isaac GR00T N1，并在标题中使用“world’s first open humanoid robot foundation model”与“simulation frameworks”表述[18][19]。

需要特别披露的是：关于 NVIDIA “世界首个开放（open）的人形机器人基础模型”的口径，本轮证据仅包含其新闻稿标题层表述，缺少对“open”的明确范围定义（例如权重/数据/许可证开放边界）及独立第三方交叉验证，因此该“first/open”更应被视为一种营销性主张而非已被严格证实的技术事实[19]。

---

## 研究范围与方法（含关键假设与证据缺口披露）

本报告面向产业从业者与投资人，目标是在截至 2026-05-31 的时间点，基于可核验公开材料，梳理具身智能的主要技术路线框架，并对若干具有代表性的公司/平台主体进行可比口径的对照。

### 研究范围

1. 技术路线覆盖范围（以“从模型到控制—从数据到仿真—从平台到落地”为主线）：

- 视觉-语言-动作（VLA）/VLM 到控制  
  RT-1 的论文标题明确为“RT-1: Robotics Transformer for Real-World Control at Scale”，并有研究团队在 2022-12-13 发布官方解读文章，作为该路线的公开锚点[1][2]。  
  RT-2 的论文标题提出“Vision-Language-Action Models”，并明确其目标是“Transfer Web Knowledge to Robotic Control”[3][4]。论文研究表述包括：将基于互联网规模数据训练的视觉-语言模型能力直接并入端到端机器人控制，以提升泛化能力[5]。这些工作共同勾勒出“用大规模视觉-语言模型驱动通用控制”的路线[1][3][5]。

- 具身多模态与语言落地  
  PaLM-E 作为“An Embodied Multimodal Language Model”，于 2023-03-06 在 arXiv 发布[6]；SayCan 论文《Do As I Can, Not As I Say: Grounding Language in Robotic Affordances》PDF 显示日期为 2022-08-16，主题为将语言与机器人可供性进行对齐/grounding[7]。

- 生成式策略学习  
  《Visuomotor Policy Learning via Action Diffusion》于 2023-03-07 在 arXiv 发布，提出用动作扩散进行视觉-运动策略学习[8]；GitHub 上存在 Diffusion Policy 的开源实现仓库 real-stanford/diffusion_policy[9]。

- 数据采集与数据集  
  Mobile ALOHA 论文《Learning Bimanual Mobile Manipulation with Low-Cost Whole-Body Teleoperation》于 2024-01-04 发布，主题为低成本全身遥操作用于学习双臂移动操作[10]。  
  BridgeData V2 论文《BridgeData V2: A Dataset for Robot Learning at Scale》在 arXiv 提供版本，是“robot learning at scale”数据集方向的公开入口[11]。

- 仿真平台与工具链  
  Google DeepMind Blog 于 2022-05-23 发布《Open-sourcing MuJoCo》，宣布 MuJoCo 被开源[12]。

- 人形机器人 foundation model 平台  
  NVIDIA 于 2024-03-18 的新闻稿宣布 Project GR00T（面向人形机器人的 foundation model），并同时宣布 Isaac Robotics 平台更新[18]；2025-03-18 又宣布 Isaac GR00T N1，并在标题中使用“the World’s First Open Humanoid Robot Foundation Model”与“Simulation Frameworks to Speed Robot Development”表述[19]。

2. 公司/平台样本范围（严格限定在本轮证据中出现且可引用者）：

- Boston Dynamics（Atlas：电驱迭代与试点路径）[13]  
- Apptronik（Apollo：融资披露与试点合作伙伴关系）[14][15]  
- Fourier Intelligence（GR-1：LLM 相关表述与执行器模块化线索）[16][17]  
- NVIDIA Isaac/GR00T（平台与人形 foundation model 路线表述）[18][19]

### 方法与关键假设

- 时间窗口  
  以近 5 年为主，但允许引用更早的关键里程碑作为技术背景锚点。例如，《Solving Rubik's Cube with a Robot Hand》于 2019-10-16 在 arXiv 发布，是灵巧操作/仿真到真机（含域随机化）方向常被视作代表性论文之一，本轮材料中可获得其标题与日期信息[20]。

- 证据层级  
  优先采用论文、公司/研究机构官方博客、官方新闻稿等一手材料；当仅获得新闻摘要/snippet 级线索时，在相关段落中明确其信息粒度限制，并避免推断更细的商业条款与技术细节[14][15][16][17]。

- 推理边界  
  除对不同公开表述进行归纳性整理外，不引入现有证据之外的市场规模、出货量、客户部署数量、估值与盈利能力等结论。

### 已知证据缺口

- 公司层面  
  Apptronik：本轮材料仅覆盖 5.2 亿美元融资及部分投资方，以及与 Jabil 的试点合作“已宣布”这一事实，未覆盖轮次/估值/条款、Apollo 机型配置、量产计划、客户与收入等[14][15]。  
  Fourier：仅覆盖 GR-1“Powered by LLM”表述及 Smart Actuator（FSA）模块化线索，未覆盖产品规格、交付节奏、商业化路径、融资与团队信息，且部分信息来自摘要线索[16][17]。  
  NVIDIA Isaac/GR00T：新闻稿中未披露模型开放范围、可获取方式、商业授权等细节[18][19]。

- 技术层面  
  RT-1/RT-2/PaLM-E 等论文在本轮材料中多以标题、发布日期与高层定位表述为主，缺少数据规模、评测指标与复现协议等细节，因此本报告在技术路线部分只进行方向性梳理，不做性能排名[1][3][6]。  
  BridgeData V2 仅作为“robot learning at scale 数据集”的论文入口出现，缺乏规模和协议细节[11]。

- 口径冲突  
  NVIDIA 在 2025-03-18 新闻稿标题中使用“world’s first open humanoid robot foundation model”[19]，但本轮材料缺少对“open”的范围定义与第三方验证，因此该口径被视为存在潜在冲突与不确定性，将在后文专门披露。

---

## 具身智能技术路线框架

本章以“从感知/语言到动作控制”为纵轴、以“数据与仿真—平台化工程能力”为横轴，归纳当前证据可覆盖的具身智能技术路线模块。

### 1) VLA/VLM 到控制：从策略网络到端到端泛化

- RT-1：  
  论文标题为“RT-1: Robotics Transformer for Real-World Control at Scale”[1]，Google Research Blog 于 2022-12-13 发布官方解读文章[2]。在本轮材料范围内，可确认该工作以 Transformer 为核心架构，聚焦“真实世界规模化控制”这一定位，但数据规模与指标尚未在材料中展开[1][2]。

- RT-2：  
  RT-2 的论文标题为“RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control”，直接说明其模型类别为 Vision-Language-Action，并以“Transfer Web Knowledge to Robotic Control”为目标[3][4]。现有材料指出，该研究将基于互联网规模数据训练的视觉-语言模型能力直接并入端到端机器人控制，以提升泛化能力[5]。这类能力迁移路线为产业提供了一个清晰框架：先在互联网数据上获得强语义与视觉理解，再通过端到端训练将其映射到具体动作空间[3][5]。

### 2) 具身多模态与语言落地：从“理解”到“可执行”

- PaLM-E：  
  arXiv 页面显示《PaLM-E: An Embodied Multimodal Language Model》日期为 2023-03-06[6]，材料中将其定位为“具身多模态语言模型”。在本轮证据中，尚未提供实验细节与评测，仅能确立其作为多模态具身模型方向的代表节点[6]。

- SayCan：  
  arXiv PDF 显示《Do As I Can, Not As I Say: Grounding Language in Robotic Affordances》日期为 2022-08-16[7]。文档描述其主题为将语言与机器人可供性（affordances）进行对齐/grounding，以实现“Do as I can”式的可执行指令落地[7]。这提示：在将大语言模型用于具身场景时，需要将自然语言输出约束在机器人“能做到”的可供性集合之内。

### 3) 扩散策略与生成式控制：从判别式策略到生成式动作序列

- Action Diffusion：  
  《Visuomotor Policy Learning via Action Diffusion》于 2023-03-07 在 arXiv 发布[8][21]，提出用动作扩散进行视觉-运动策略学习。本轮材料未展开其网络结构细节与指标，但确认其在时间序列动作建模中的代表性。

- Diffusion Policy 开源实现：  
  GitHub 仓库 real-stanford/diffusion_policy 的标题含“[RSS 2023] Diffusion Policy”，并被描述为 Diffusion Policy 的开源实现入口[9]。这表明相应方法不仅停留在论文阶段，也已进入开源工程实践层面[9]。

### 4) 遥操作数据采集：用“可规模化示教”缩短策略迭代周期

- Mobile ALOHA：  
  《Learning Bimanual Mobile Manipulation with Low-Cost Whole-Body Teleoperation》于 2024-01-04 在 arXiv 发布[10][22]。文档描述其主题为“低成本全身遥操作用于学习双臂移动操作”[10]。在当前证据中，未给出具体任务数与性能曲线，但可确认其在“低成本全身遥操作数据采集”方向的代表地位[10][22]。

### 5) 数据集：面向“robot learning at scale”的数据资产

- BridgeData V2：  
  《BridgeData V2: A Dataset for Robot Learning at Scale》在 arXiv 提供版本[11][23]。现有材料指出，该论文为“robot learning at scale”的数据集来源，但未提供版本日期、数据规模与采集协议细节[11][23]。因此本报告仅将其作为数据集路线的标志性条目，而不对其覆盖范围与质量进行推断。

### 6) 仿真平台：从工具链开源到生态扩散

- MuJoCo 开源节点：  
  Google DeepMind Blog 于 2022-05-23 发布《Open-sourcing MuJoCo》，宣布 MuJoCo 被开源[12][24]。在具身智能开发中，这类物理仿真引擎的开源常被视为降低研发门槛的关键节点，尽管本轮材料未量化其实际生态规模[12][24]。

### 7) 人形 foundation model 与开发平台：把“模型能力”产品化为平台

- Project GR00T：  
  NVIDIA Newsroom 于 2024-03-18 发布新闻稿，宣布 Project GR00T foundation model for humanoid robots，并宣布 Isaac Robotics 平台更新[18][25]。材料表明，该项目被定位为面向人形机器人的基础模型，与机器人软件平台协同发展[18][25]。

- Isaac GR00T N1：  
  2025-03-18 的新闻稿标题为 “NVIDIA Announces Isaac GR00T N1 — the World’s First Open Humanoid Robot Foundation Model — and Simulation Frameworks to Speed Robot Development”[19][26]。可确认其中包含“world’s first open humanoid robot foundation model”和“simulation frameworks”表述[19][26]。然而，本轮证据未说明“open”具体含义（是否开源权重、训练数据、训练代码或 API）、也未提供第三方验证，因此在评估其开放程度与生态潜力时需保持谨慎[19]。

### 8) 补充背景锚点：灵巧操作与 sim2real

- Rubik’s Cube Robot Hand：  
  arXiv 页面信息表明《Solving Rubik's Cube with a Robot Hand》日期为 2019-10-16[20][27]。材料指出该论文常作为灵巧操作与 sim2real（含域随机化等）方向的代表性里程碑之一，但本轮无法展开其方法与实验细节[20][27]。

---

## 代表性公司与路线案例

本章以“技术路径、产品进度、商业化进度、融资、团队”五栏口径，对本轮证据覆盖到的代表主体做对照。凡未在本轮材料中出现的细项，均明确标注为“未在本轮证据中覆盖”。

### 1) Boston Dynamics（Atlas）

- 技术路径  
  Boston Dynamics 在官方博客中宣布退役液压版 Atlas，并发布“fully electric Atlas”[13]。文章表示电驱 Atlas 将比以往更强壮（stronger）且具有更广的运动范围（broader range of motion），并将探索多种夹爪（gripper variations）以适配客户环境中的操作需求[13]。

- 产品进度  
  已公开发布“fully electric Atlas”，作为从液压到电驱的重大产品迭代节点[13]。本轮材料未进一步披露批量生产或交付状态。

- 商业化进度  
  官方博客表述：Atlas 的合作/试点将从 Hyundai 开始，并将先与小范围创新客户合作迭代应用，类似 Stretch 的商业化路径[13]。在本轮证据中，未看到对具体试点任务、合同形式或收入规模的公开信息。

- 融资  
  未在本轮证据中覆盖。

- 团队（关键人物/组织变化）  
  未在本轮证据中覆盖。

### 2) Apptronik（Apollo）

- 技术路径  
  本轮材料未包含 Apollo 在感知、控制、学习架构或硬件规格方面的公开细节，无法对其技术路线进行进一步描述。

- 产品进度  
  未在本轮证据中覆盖 Apollo 的具体产品规格、工程样机状态或量产时间线。

- 商业化进度  
  TechCrunch 报道的摘要线索显示：Apptronik 宣布与美国制造/供应链公司 Jabil 建立新的试点合作伙伴关系[15]。摘要未提供试点范围、时间线、Apollo 机型配置或商业条款细节[15]。

- 融资  
  Austin Business Journal 报道（目前仅有摘要线索，未读取到正文）称 Apptronik 在 2026-02-11 披露获得 5.2 亿美元融资，摘要提及投资方包括 Mercedes-Benz、John Deere、Qatar Investment Authority 等[14]。现有材料尚未明确该融资的轮次、结构、估值与资金用途[14]。

- 团队（关键人物/组织变化）  
  未在本轮证据中覆盖。

### 3) Fourier Intelligence（GR-1）

- 技术路径  
  Fourier Intelligence 官网 GR-1 产品介绍被描述为官方规格/能力说明入口，摘要线索显示页面包含“Powered by LLM”等表述[16]。这意味着在官方叙事中，GR-1 与大语言模型能力存在关联，不过本轮材料未细化其耦合方式（如是否用于任务规划、对话或其他）[16]。

- 产品进度  
  本轮证据未覆盖 GR-1 的具体规格（如自由度、传感器配置、负载）、量产与交付状态。

- 商业化进度  
  未在本轮证据中覆盖。

- 融资  
  未在本轮证据中覆盖。

- 团队（关键人物/组织变化）  
  未在本轮证据中覆盖。

- 补充：执行器与模块化线索  
  Fourier GR-1 PDF 资料和相关摘要线索指出：Smart Actuator（FSA）将 motor/driver/reducer/encoder 集成为单一模块，为 GR-1 提供动力与控制[17]。该信息说明 Fourier 在执行器侧采用了高度集成的模块化设计，但具体性能参数因原文未能读取而暂不可考[17]。

### 4) NVIDIA（平台型：Isaac/GR00T）

- 技术路径  
  NVIDIA Newsroom 于 2024-03-18 发布新闻稿，宣布 Project GR00T：面向人形机器人的 foundation model，并同时宣布 Isaac Robotics 平台更新[18][25]。这表明公司在具身智能方向的路线包含两部分：一是人形专用的基础模型（foundation model），二是与之配套的机器人软件/仿真平台[18][25]。

- 产品进度  
  2025-03-18 的新闻稿宣布 Isaac GR00T N1，并在标题中提到“Simulation Frameworks to Speed Robot Development”[19][26]。现有材料未披露 GR00T N1 的具体产品形态（例如模型参数规模、开放接口形式），也未说明仿真框架支持的机器人类型与任务集[19][26]。

- 商业化进度  
  本轮证据未覆盖 NVIDIA Isaac/GR00T 的商业化数据，例如合作客户、收费模式与收入规模。

- 融资  
  不适用/未在本轮证据中覆盖（新闻稿中未涉及融资内容）。

- 团队（关键人物/组织变化）  
  未在本轮证据中覆盖。

#### 必须披露的冲突点：关于“world’s first open”

NVIDIA 在 2025-03-18 新闻稿标题中宣称 Isaac GR00T N1 为“the World’s First Open Humanoid Robot Foundation Model”[19][26]。然而，本轮材料中：

- 未给出“open/开放”的明确技术与法律定义（如是否开源权重、训练数据、训练代码、推理 API 接入条件等）；  
- 未包含独立第三方来源对该“first/open”主张的交叉验证。

因此，该表述目前只能被视为供应商的官方宣称，在事实层面存在口径不确定性，应在产业合作与投资尽调中进一步核实[19]。

---

## 对产业与投资的启示

本章仅基于前述公开证据中“技术路线的可见方向”与“公司/平台的公开表述”，抽象出对产业落地与投资决策更具操作性的启示；不引入市场规模等外部数字。

### 1) 从“模型叙事”走向“可执行闭环”

RT-2 将 Vision-Language-Action 作为模型类别，并以“将 web knowledge 迁移到机器人控制”为目标，同时提出将互联网规模视觉-语言模型能力并入端到端控制以提升泛化能力[3][5]。SayCan 则通过将语言与机器人可供性进行 grounding，使自然语言指令被映射到机器人“能做”的动作集合[7]。对产业方而言，这表明：

- 评估具身智能路线时，不能只关注语言/视觉模型的能力演示；  
- 需要重点关注该能力如何与低层控制闭环对齐（例如通过可供性约束、端到端控制策略或其他安全机制），以及这种对齐是否可在目标场景中稳定复用[3][5][7]。

### 2) 数据工程将决定迭代速度

Mobile ALOHA 强调“低成本全身遥操作”用于学习双臂移动操作[10][22]；BridgeData V2 被定位为“robot learning at scale”的数据集入口[11][23]。这两类工作共同指向一个结论：在具身智能路线中，数据采集与管理能力（包括成本、效率与质量控制）将直接影响策略迭代的速度与上限。

因此，在产业尽调中，可以把以下问题作为重点：

- 数据采集方式是否具备可持续的成本结构（例如是否有类似低成本全身遥操作的机制）[10]；  
- 是否有内部或外部可复用的数据集资产，与目标任务分布是否匹配[11]。

### 3) 生成式策略虽已可用，但仍需系统级验证

动作扩散路线在 2023 年以论文形式公开，并出现 Diffusion Policy 的开源实现仓库[8][9]。这意味着生成式动作策略已具备一定的工程可用性。对投资与产业合作而言：

- 开源实现降低了尝试门槛，但并不自动意味着“可在特定场景形成稳定效果”；  
- 仍需关注系统集成层面的证据，包括与传感器、执行器特性、控制频率和安全机制的匹配情况（本轮材料未覆盖这些细节，因此本报告仅提出“需验证”的方向，而不做实证性结论）[8][9]。

### 4) 仿真与平台有利于缩短开发周期，但“开放”需要可检验定义

MuJoCo 的开源为仿真工具链生态提供了基础能力[12][24]。NVIDIA 通过 Project GR00T 与 Isaac GR00T N1，将 foundation model 与仿真框架打包为平台，并声称可以“加速机器人开发”[18][19][26]。在此背景下，对产业与投资而言，关键问题包括：

- 平台的“开放性”应拆解为可检验维度：接口开放度、模型/权重可获取性、许可范围、可部署性等；  
- 在缺乏明确“open”定义与第三方验证的情况下，不宜仅凭新闻稿标题判断平台的生态价值和进入壁垒[19]。

### 5) 人形落地更可能是“小范围试点+共创”路径

Boston Dynamics 在介绍电驱 Atlas 的博客中明确表示：合作将从 Hyundai 开始，并会像 Stretch 一样先与小范围创新客户合作迭代 Atlas 的应用[13]。从这一公开表述可以抽象出对人形机器人路线的一个现实预期：

- 早期落地更可能以试点共创和场景共建为主，而不是大规模标准化部署；  
- 产业方在规划具身/人形项目时，可以参考类似“先试点—再扩展”的节奏来设计 ROI 评估方法与组织安排[13]。

### 6) 把“证据可核验程度”纳入投研评分

在本轮材料中，不同公司信息透明度差异较大：

- Boston Dynamics 的产品迭代与试点路径来自公司官方博客，可核验度较高[13]；  
- Apptronik 的融资与 Jabil 试点合作目前主要来自新闻摘要线索[14][15]；  
- Fourier 的 GR-1 关键表述在官网及产品 PDF 摘要中出现，但规格与交付信息缺失[16][17]；  
- NVIDIA Isaac/GR00T 的路线信息来自官方新闻稿，缺少第三方交叉验证[18][19]。

因此，在投研实践中，除了技术路线判断以外，有必要建立一套“信息可核验度”指标，用于量化不同标的在公开信息透明度和可尽调性方面的差异，从而更好地配置调研资源[13][14][15][16][17][19]。

---

## 局限性与后续调研清单

### 局限性

1. 公司信息不完整导致横向可比性受限

- Apptronik：  
  现有材料仅覆盖 2026-02-11 披露的 5.2 亿美元融资与投资方名单，以及与 Jabil 的试点合作“已宣布”这一事实[14][15]。对轮次、估值、资金用途、试点范围与时间线、Apollo 产品规格、量产计划与客户部署等关键变量，本轮证据尚未覆盖[14][15]。

- Fourier：  
  现有材料仅覆盖 GR-1 产品叙事中“Powered by LLM”表述以及 Smart Actuator（FSA）模块化集成线索[16][17]；产品规格、交付节奏、商业化路径、融资与团队信息均未在本轮证据中出现。

- NVIDIA Isaac/GR00T：  
  新闻稿提供了 Project GR00T 与 Isaac GR00T N1 的发布节点和定位，但未披露模型开放范围、可获取方式、商业授权等实务信息[18][19]。

2. 技术层面的“可复现细节”不足

- RT-1/RT-2/PaLM-E：  
  在本轮材料中，这几项工作主要通过标题、定位和发布日期被引用[1][3][6]，缺乏对数据规模、训练配置与评测指标的详细摘录，本报告因此避免基于性能做路线优劣判断。

- BridgeData V2：  
  仅作为“robot learning at scale”数据集论文入口出现，缺少规模、协议、任务分布等信息，无法支撑对数据质量或覆盖范围的进一步分析[11][23]。

3. 口径不确定性：NVIDIA “world’s first open”

如前文所述，NVIDIA 在 2025-03-18 新闻稿标题中宣称 Isaac GR00T N1 为“world’s first open humanoid robot foundation model”[19][26]，但本轮材料缺少：

- “open”定义与边界（例如权重、代码、数据、API 和许可证的开放程度）；  
- 独立第三方来源对该主张的交叉验证。

因此该口径属于存在不确定性的官方宣称，在投研与合作决策中应作为需进一步验证的事项，而非已被充分证实的事实[19]。

### 后续调研清单

1. Apptronik（Apollo）

- 融资：  
  明确轮次、结构（股权/债权/可转债等）、领投/跟投、估值与资金用途[14]。  
- 试点（Jabil）：  
  获取试点范围（工站/产线类型）、时间线、KPI 设定与商业条款（付费/联合开发等）[15]。  
- 产品：  
  Apollo 的关键硬件规格（自由度、负载、续航、传感器配置）、安全认证路径与量产计划。  
- 团队：  
  核心管理层与技术负责人背景、组织结构和关键人才流动情况。

2. Fourier Intelligence（GR-1）

- 技术落地：  
  “Powered by LLM”在 GR-1 系统中的具体位置（任务规划、对话、世界模型等）[16]。  
- FSA 性能与供应链：  
  Smart Actuator（FSA）的扭矩密度、效率、寿命与成本，以及其供应链成熟度[17]。  
- 商业化：  
  当前是否已形成规模化交付、主要客户与场景。  
- 融资与团队：  
  融资轮次、投资方结构、核心研发团队与高管背景。

3. NVIDIA Isaac/GR00T

- “open”定义与可用资产：  
  核查权重、代码、数据、API 等层面的开放范围与许可证条款[19]。  
- 产品形态：  
  GR00T N1 和配套仿真框架的可下载资产、SDK/API、支持的参考机器人与任务集[19][26]。  
- 生态：  
  与硬件厂商、系统集成商和开发者的合作机制、认证计划与生态激励。

4. 技术路线侧补齐

- 数据与评测：  
  针对遥操作、真机采集与合成数据，补齐规模、协议与质量控制方法；对 BridgeData V2 等数据集建立更详细的元数据视图[10][11]。  
- 系统工程栈：  
  补充规划/控制/实时系统/安全机制等方面的权威技术路线与工程实践来源（本轮材料尚未覆盖）。  
- 性能对比：  
  在获取更多公开数据后，对 RT-1/RT-2/扩散策略等路线在典型任务上的指标、成功率和失败模式进行更系统的对比[1][3][8][10]。

---

## 参考文献

[1] RT-1: Robotics Transformer for Real-World Control at Scale – arXiv  
https://arxiv.org/abs/2212.06817  

[2] RT-1: Robotics Transformer for real-world control at scale – Google Research Blog  
https://research.google/blog/rt-1-robotics-transformer-for-real-world-control-at-scale/  

[3] RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control – arXiv  
https://arxiv.org/abs/2307.15818  

[4] RT-2: Vision-Language-Action Models – 官方项目页  
https://robotics-transformer2.github.io/  

[5] RT-2 论文与项目页中关于“将互联网规模视觉-语言模型能力并入端到端机器人控制，以提升泛化”的研究表述 – 综合自 [3][4]  

[6] PaLM-E: An Embodied Multimodal Language Model – arXiv  
https://arxiv.org/abs/2303.03378  

[7] Do As I Can, Not As I Say: Grounding Language in Robotic Affordances – arXiv PDF  
https://arxiv.org/pdf/2204.01691  

[8] Visuomotor Policy Learning via Action Diffusion – arXiv  
https://arxiv.org/abs/2303.04137  

[9] real-stanford/diffusion_policy: [RSS 2023] Diffusion Policy – GitHub  
https://github.com/real-stanford/diffusion_policy  

[10] Learning Bimanual Mobile Manipulation with Low-Cost Whole-Body Teleoperation – arXiv  
https://arxiv.org/abs/2401.02117  

[11] BridgeData V2: A Dataset for Robot Learning at Scale – arXiv  
https://arxiv.org/abs/2308.12952  

[12] Open-sourcing MuJoCo – Google DeepMind Blog  
https://deepmind.google/blog/open-sourcing-mujoco/  

[13] An Electric New Era for Atlas – Boston Dynamics Blog  
https://bostondynamics.com/blog/electric-new-era-for-atlas/  

[14] Apptronik secures $520M from Mercedes-Benz, John Deere and Qatar Investment Authority – Austin Business Journal  
https://www.bizjournals.com/austin/news/2026/02/11/apptronik-austin-robotics-startup-adds-millions.html  

[15] Apptronik’s humanoid robots take the first steps toward building themselves – TechCrunch  
https://techcrunch.com/2025/02/25/apptroniks-humanoid-robots-take-the-first-steps-toward-building-themselves/  

[16] Fourier GR-1 - FOURIER-Robotics – 官方产品页  
https://www.fftai.com/products-gr1  

[17] [PDF] Fourier GR-1 – 产品资料（Smart Actuator / FSA）  
https://fftai.com/uploads/upload/files/20240925/a81ec73e48d9f8046b5b673601075e8d.pdf  

[18] NVIDIA Announces Project GR00T Foundation Model for Humanoid Robots and Major Isaac Robotics Platform Update – NVIDIA Newsroom  
https://nvidianews.nvidia.com/news/foundation-model-isaac-robotics-platform  

[19] NVIDIA Announces Isaac GR00T N1 — the World’s First Open Humanoid Robot Foundation Model — and Simulation Frameworks to Speed Robot Development – NVIDIA Newsroom  
https://nvidianews.nvidia.com/news/nvidia-isaac-gr00t-n1-open-humanoid-robot-foundation-model-simulation-frameworks  

[20] Solving Rubik's Cube with a Robot Hand – arXiv  
https://arxiv.org/abs/1910.07113  

[21] Visuomotor Policy Learning via Action Diffusion – 日期与主题说明 – 见 [8]  

[22] Learning Bimanual Mobile Manipulation with Low-Cost Whole-Body Teleoperation – 日期与主题说明 – 见 [10]  

[23] BridgeData V2: A Dataset for Robot Learning at Scale – 数据集定位说明 – 见 [11]  

[24] Open-sourcing MuJoCo – 开源事件说明 – 见 [12]  

[25] Project GR00T 与 Isaac Robotics 平台更新 – 见 [18]  

[26] Isaac GR00T N1 标题中的 “world’s first open humanoid robot foundation model” 与 “simulation frameworks” 表述 – 见 [19]  

[27] Solving Rubik's Cube with a Robot Hand – 日期说明与里程碑定位 – 见 [20]