## 摘要

截至2026-06-01，具身智能（机器人+多模态大模型）在公开资料中呈现出几条相互交织的技术主线：其一是以视觉-语言-动作（VLA）模型为核心，把视觉与语言理解直接映射为机器人动作，用以提升跨任务泛化与“从网络知识到机器人控制”的迁移能力；代表性工作包括DeepMind/Google的RT-2与其与RT-1数据的连接，以及开源的OpenVLA等[1][2][3][4][5]。其二是围绕“端到端策略学习 + 大规模机器人/人类行为数据”的数据规模化路线：一方面通过真实机器人采集大规模示范（如RT-1在多机器人上采集并覆盖数百任务），另一方面探索以人类视频等更易规模化的数据形态缓解机器人数据稀缺，并宣称可向具体系统迁移（如Figure的Project Go-Big到Helix）[1][6][7]。其三是强调自我改进与跨机器人迁移的通用体学习路线（RoboCat被描述为可自我改进、可在不同机械臂间迁移的多任务体学习代理）[8][9]。其四是在策略表示上引入扩散模型，将动作序列/轨迹生成建模为条件去噪扩散过程（Diffusion Policy）[10]。其五是把仿真评测与sim-to-real工作流作为规模化研发“底座”：NVIDIA一方面提出面向通用策略的仿真评测套件Isaac Lab-Arena，另一方面在Isaac Lab 2.3中强化全身控制与遥操作工作流，并讨论从真实示范训练的成本与泛化挑战；同时在GR00T N1/N1.6叙事中将“人形foundation model + 仿真到现实工作流”作为通用人形能力构建路径[11][12][13][14][15]。在公司/机构层面，本报告基于证据覆盖，给出DeepMind/Google（RT-1/RT-2、RoboCat）、OpenVLA、NVIDIA（Project GR00T、Isaac Lab-Arena、Isaac Lab 2.3、GR00T N1.6工作流）、Figure（Figure 03、Project Go-Big/Helix叙事）、Boston Dynamics+Toyota Research Institute（Atlas与“大行为模型”方向）、Sanctuary AI（Phoenix与触觉/遥操作数据）等代表性主体的公开信息梳理[1][2][4][6][7][8][11][12][13][16][17]。

需要强调：受限于可核验公开证据覆盖范围，本报告对“商业化（客户/收入）”“融资（轮次/金额/投资方）”“团队（核心成员背景）”等维度仅能在少数主体上给出定性或定位级信息；对于未被证据覆盖的细节（例如融资金额、量产时间表、具体客户名单、核心团队履历等）均不做推断，并在相应章节集中披露缺口。

---

## 方法与范围 / 假设

本报告以截至2026-06-01前的公开材料为依据，研究对象限定为“具身智能：机器人系统在感知（视觉等）、语言/指令理解与动作控制之间形成端到端或近端到端闭环，并以多模态大模型、通用策略学习或可迁移技能为关键技术要素”的技术与产业主体。

信息来源与可核验性：仅使用被明确标注为论文、官方/技术博客、新闻报道与公司官方页面的公开材料，并仅在材料明确表述处做事实陈述，所有事实性信息均以编号引用对应到参考文献。[1][2][3][4][5][6][7][8][9][10][11][12][13][14][15][16][17]

范围假设与结构安排：  
1) 技术路线综述部分以“路线定义—关键要素—代表性工作/机构”的方式组织，优先覆盖证据中出现的路线：VLA；端到端策略学习+大规模机器人数据；自我改进/迁移；扩散策略；仿真评测与sim-to-real；以及以“人形foundation model”叙事驱动的平台化路线（以NVIDIA GR00T与Figure Helix相关公开表述为代表）。[3][4][5][7][10][11][14][15]  
2) 公司/机构部分仅覆盖证据明确涉及的主体：DeepMind/Google（RT-1、RT-2、RoboCat）、OpenVLA、NVIDIA（Project/Isaac GR00T、Isaac Lab-Arena、Isaac Lab 2.3、GR00T N1.6工作流）、Figure AI（Figure 03、Project Go-Big/Helix）、Boston Dynamics+Toyota Research Institute（Atlas与LBMs方向）、Sanctuary AI（Phoenix与触觉/遥操作数据）。[1][2][6][7][8][11][12][13][16][17]  
3) 对“产品进度/商业化/融资/团队”等维度：除非材料中明确给出，否则不补充、不推断；对证据缺失将集中在专门小节披露。

---

## 技术路线综述

### 1) VLA（Vision-Language-Action）与“多模态模型直接出动作”

VLA模型通常被界定为：输入视觉与语言信息，输出机器人动作，用于完成具身任务[3][4]。在该脉络下，RT-2被描述为视觉-语言-动作模型，其目标是把视觉与语言“翻译”为动作，并从网络（web）数据与机器人数据共同学习；其论文摘要强调将互联网规模视觉-语言预训练能力迁移到机器人控制以提升泛化[2][4][5]。开源路线中，OpenVLA被描述为7B参数的开源VLA模型，并在论文中披露其训练数据包含约97万条真实世界机器人示范[18]。

### 2) 端到端策略学习 + 大规模机器人数据（真实示范规模化）

与VLA相互耦合的另一条主线是“端到端策略学习依赖大规模、可覆盖多任务的机器人交互/示范数据”。RT-1的公开材料给出一个典型规模化案例：其训练基于大规模真实机器人数据集，数据包含130k episodes、覆盖700+任务，采集自13台机器人[1]。这类工作体现出以真实机器人数据提升通用控制能力的路线，但也带来数据采集成本与泛化风险等挑战（见后文仿真/遥操作与训练成本讨论）。[12]

### 3) 自我改进/跨机器人迁移的通用体学习

RoboCat被描述为“自我改进”的机器人代理，能够学习多任务并在不同机械臂之间迁移；论文摘要进一步将其刻画为一种以视觉目标条件为核心的决策Transformer（decision transformer），以带动作标注的视觉经验作为学习输入。[8][9]

### 4) 扩散策略（Diffusion Policy）作为动作生成建模范式

Diffusion Policy提出将机器人视觉-运动（visuomotor）策略表示为条件去噪扩散模型，通过扩散过程生成动作或轨迹序列，用于控制与模仿学习。[10]

### 5) 仿真评测、遥操作与sim-to-real工作流：规模化研发底座

当策略越来越“通用”，其评测与训练往往需要跨任务、跨环境的可扩展基准与工具链。Isaac Lab-Arena被提出用于在仿真中对通用型（generalist）机器人策略进行可扩展评测，并以“通用策略必须跨多样任务运行”为背景给出其动机。[11]

在训练范式上，Isaac Lab 2.3的公开材料强调了与全身控制（whole-body control）与增强遥操作（teleoperation）相关的能力，同时明确讨论了从真实世界示范训练机器人策略的成本，以及泛化与过拟合等挑战。[12]

### 6) “人形foundation model”叙事与平台化路线

在产业侧，NVIDIA的公开发布将Project GR00T/Isaac GR00T N1定位为面向人形机器人的foundation model，并同时强调仿真框架/平台更新以加速机器人开发。[13][14] 在更具体的实践叙事中，GR00T N1.6相关技术博客将“sim-to-real workflow”与“generalist humanoid capabilities”的构建路径联系起来，作为通用人形能力开发的示例性工作流。[15]

与之相邻的另一种数据规模化叙事来自Figure：其Project Go-Big页面强调以人类视频采集来构建大规模人形预训练数据，并宣称这些能力可直接迁移到其名为Helix的系统。[7]

小结：从现有证据看，技术路线并非彼此排斥——VLA模型、端到端策略学习、数据规模化、自我改进/迁移与仿真-sim-to-real工作流常被组合为一套“通用体学习系统工程”。但在公开材料中，关于训练数据分布、评测体系与真实部署约束的可复现细节仍高度依赖少数论文与平台工具披露。

---

## 代表性公司 / 机构

### 1) DeepMind / Google：RT-1、RT-2（VLA）

技术路径：RT-1被描述为基于大规模真实机器人数据训练的控制模型，公开材料披露其训练数据规模为130k episodes、覆盖700+任务，采集自13台机器人[1]。RT-2被描述为视觉-语言-动作（VLA）模型，目标是把视觉与语言直接转换为动作，并从web数据与机器人数据共同学习；其论文与项目主页均强调将互联网规模视觉-语言预训练能力迁移到端到端机器人控制以提升泛化。[2][4][5][6]

产品/演示进度：在可用证据中，RT-1/RT-2以研究原型与方法发布为主；未见同一证据集合中对量产或商业落地案例的明确披露。[1][2][4][6]

商业化/融资/团队：在可用证据中未出现与RT-1/RT-2直接相关的商业化客户、收入、融资轮次或核心团队履历等可核验信息（详见“信息现状与缺口”小节）。

### 2) OpenVLA：开源VLA模型

技术路径：OpenVLA论文将其描述为7B参数的开源VLA模型[18]。数据与训练：论文披露其训练数据包含约97万条真实世界机器人示范。[18]  
产品/商业化/融资/团队：在可用证据中，OpenVLA以研究/开源发布为主，未包含产品化、客户、融资或团队信息。

### 3) DeepMind：RoboCat（自我改进/迁移）

技术路径：RoboCat被描述为可自我改进的机器人代理，能够学习多任务并在不同机械臂之间迁移[8]；论文摘要进一步将其刻画为视觉目标条件的决策Transformer，并以带动作标注的视觉经验作为学习输入。[9]  
产品/商业化/融资/团队：在可用证据中，RoboCat同样以研究发布为主，未包含商业化与融资/团队细节。

### 4) NVIDIA：Project GR00T / Isaac GR00T、Isaac Lab-Arena、Isaac Lab 2.3、GR00T N1.6工作流

技术路径与定位：NVIDIA发布将Project GR00T定位为面向人形机器人的foundation model，并配套Isaac机器人平台更新[13]；后续发布将Isaac GR00T N1描述为开放的人形机器人foundation model，并强调仿真框架以加速开发。[14]

仿真评测与工具链：Isaac Lab-Arena被提出用于在仿真中对通用型机器人策略进行可扩展评测[11]。Isaac Lab 2.3则强调全身控制与增强遥操作能力，并讨论从真实世界示范训练策略的成本及泛化/过拟合挑战。[12]

sim-to-real叙事：GR00T N1.6相关技术博客将“sim-to-real workflow”与构建“generalist humanoid capabilities”的路径联系起来，作为通用人形能力开发的示例。[15]

产品/商业化/融资/团队：在可用证据中，以上内容主要是平台与工具链/模型定位的公开发布；未见对具体下游客户、收入、融资轮次或核心团队履历的明确披露。[11][12][13][14][15]

### 5) Figure AI：Figure 03、Project Go-Big与Helix叙事

产品/平台定位：Figure官方页面将Figure 03描述为第三代人形机器人，并写明其“designed for Helix, the home, and the world at scale”等定位。[16]  
数据规模化叙事：Project Go-Big页面强调以人类视频采集构建互联网/行星规模的人形预训练数据，并宣称这些能力可直接迁移到其Helix系统。[7]  
商业化/融资/团队：在可用证据中，上述页面未提供可核验的融资金额/轮次、客户/收入或核心团队履历细节。

### 6) Boston Dynamics + Toyota Research Institute（TRI）：Atlas与“大行为模型（LBMs）”方向

合作与技术方向：Toyota新闻稿称TRI与Boston Dynamics合作，使Atlas实现使用AI的自主全身操作与运动行为，并将其表述为迈向通用人形机器人的关键一步。[17]  
在Boston Dynamics的博客表述中，Atlas相关工作被描述为推进“大行为模型（Large Behavior Models, LBMs）”方向，并指出与TRI合作相关。[6][19]  
产品/商业化/融资/团队：在可用证据中，以上材料聚焦技术方向与合作进展表述，未提供量产/客户/收入、融资或核心团队履历等细节。

### 7) Sanctuary AI：Phoenix（触觉/遥操作数据）

技术要点：新闻报道指出Sanctuary AI在Phoenix通用机器人上集成触觉传感器，并引述其观点称触觉将促进遥操作，并为训练具身AI模型提供更丰富数据。[20]  
产品/商业化/融资/团队：在可用证据中，除上述触觉与遥操作数据相关表述外，未包含Phoenix的量产/部署、客户、融资与团队细节。

---

## 商业化 / 融资 / 团队信息：现状与缺口

在可核验证据覆盖下，“商业化、融资、团队”三类信息呈现出明显的不对称：

1) 商业化（客户/收入/落地场景）  
现有材料以研究论文、技术博客、公司官方页面对技术定位与方法为主。比如RT-1/RT-2与RoboCat的材料主要描述模型范式、数据来源与能力目标；NVIDIA相关材料主要描述平台/工具链与仿真—训练—部署工作流；Figure材料集中在Figure 03平台定位与Project Go-Big的数据规模化叙事；TRI/Boston Dynamics材料强调合作与技术方向（AI自主全身操作、LBMs）；Sanctuary AI材料集中在触觉传感与遥操作数据价值表述。[1][2][8][11][12][15][16][17][20]  
因此：本报告无法在同一证据集合内，可靠给出这些主体的具体客户名称、合同/收入规模、生产/交付数量或明确落地案例细节。

2) 融资（轮次/金额/投资方）  
在可用证据中，未出现关于Figure AI、Sanctuary AI等公司的融资轮次、金额、时间与投资方等结构化披露；同样也未出现对NVIDIA、Google/DeepMind等大公司在“具身智能项目层面”的独立融资信息（通常也不以项目融资形式披露）。因此：除非另有可核验公开来源，本报告不对融资金额与估值作任何补充或推断。

3) 团队（核心成员/关键人才/背景）  
现有证据未覆盖上述主体在具身智能项目/产品线上的核心团队成员与履历细节。因此：本报告不陈述任何创始人/关键人才背景信息。

4) 与“研发底座”相关的可写信息边界  
尽管商业化/融资/团队证据缺口较大，但在“技术路径与工程方法”层面仍有相对明确的可写信息：例如RT-1披露真实机器人数据规模；RT-2明确提出VLA并强调从web+机器人数据学习与迁移泛化；OpenVLA披露模型规模与示范数量；RoboCat披露自我改进与跨机械臂迁移；Isaac Lab-Arena/Isaac Lab 2.3披露仿真评测、全身控制、遥操作与训练成本/泛化挑战；TRI/Boston Dynamics披露Atlas的AI自主全身行为与LBMs方向；Sanctuary AI披露触觉对遥操作与数据丰富性的价值判断。[1][2][8][11][12][18][17][20]

以上缺口并不等同于现实中不存在对应信息，而仅表示：在本次可核验证据覆盖范围内，无法对这些维度形成可引用的结论。

---

## 参考文献

[1] RT-1: Robotics Transformer for real-world control at scale — https://research.google/blog/rt-1-robotics-transformer-for-real-world-control-at-scale/  
[2] RT-2: Vision-Language-Action Models Transfer Web Knowledge to Robotic Control — https://arxiv.org/abs/2307.15818  
[3] A Survey on Vision-Language-Action Models for Embodied AI — https://arxiv.org/html/2405.14093v8  
[4] RT-2: New model translates vision and language into action — https://deepmind.google/blog/rt-2-new-model-translates-vision-and-language-into-action/  
[5] RT-2: Vision-Language-Action Models — https://robotics-transformer2.github.io/  
[6] Large Behavior Models and Atlas Find New Footing — https://bostondynamics.com/blog/large-behavior-models-atlas-find-new-footing/  
[7] Project Go-Big: Internet-Scale Humanoid Pretraining and Direct Human-to-Robot Transfer — https://www.figure.ai/news/project-go-big  
[8] RoboCat: A self-improving robotic agent — https://deepmind.google/blog/robocat-a-self-improving-robotic-agent/  
[9] RoboCat: A Self-Improving Generalist Agent for Robotic Manipulation — https://arxiv.org/abs/2306.11706  
[10] Visuomotor Policy Learning via Action Diffusion (Diffusion Policy) — https://diffusion-policy.cs.columbia.edu/diffusion_policy_2023.pdf  
[11] Simplify Generalist Robot Policy Evaluation in Simulation with NVIDIA Isaac Lab-Arena | NVIDIA Technical Blog — https://developer.nvidia.com/blog/simplify-generalist-robot-policy-evaluation-in-simulation-with-nvidia-isaac-lab-arena/  
[12] Streamline Robot Learning with Whole-Body Control and Enhanced Teleoperation in NVIDIA Isaac Lab 2.3 — https://developer.nvidia.com/blog/streamline-robot-learning-with-whole-body-control-and-enhanced-teleoperation-in-nvidia-isaac-lab-2-3/  
[13] NVIDIA Announces Project GR00T Foundation Model for Humanoid Robots and Major Isaac Robotics Platform Update — https://nvidianews.nvidia.com/news/foundation-model-isaac-robotics-platform  
[14] NVIDIA Announces Isaac GR00T N1 — the World’s First Open Humanoid Robot Foundation Model — and Simulation Frameworks to Speed Robot Development — https://nvidianews.nvidia.com/news/nvidia-isaac-gr00t-n1-open-humanoid-robot-foundation-model-simulation-frameworks  
[15] Building Generalist Humanoid Capabilities with NVIDIA Isaac GR00T N1.6 Using a Sim-to-Real Workflow — https://developer.nvidia.com/blog/building-generalist-humanoid-capabilities-with-nvidia-isaac-gr00t-n1-6-using-a-sim-to-real-workflow/  
[16] Introducing Figure 03 — https://www.figure.ai/news/introducing-figure-03  
[17] AI-Powered Robot by Boston Dynamics and Toyota Research Institute Takes a Key Step Towards General-Purpose Humanoids — https://pressroom.toyota.com/ai-powered-robot-by-boston-dynamics-and-toyota-research-institute-takes-a-key-step-towards-general-purpose-humanoids/  
[18] OpenVLA: An Open-Source Vision-Language-Action Model — https://arxiv.org/abs/2406.09246  
[19] Atlas’ Evolution From Research Robot to Industrial Humanoid — https://bostondynamics.com/blog/atlas-evolution-from-research-robot-to-industrial-humanoid/  
[20] Sanctuary AI integrates tactile sensors into Phoenix general purpose robots — https://www.therobotreport.com/sanctuary-ai-integrates-tactile-sensors-into-phoenix-general-purpose-robots/