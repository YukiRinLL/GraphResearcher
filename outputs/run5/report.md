## 一、先给结论
- 目前全球具身智能并不是“单一路线胜出”，而是一个分层堆栈：本体平台/控制栈、数据采集与仿真、VLA/机器人基础模型、世界模型与空间生成共同推进；不同公司通常只是在其中一层或两层形成强项。[1][2][3][4]
- 如果按“商业化成熟度”看，最先落地的是仓储/工业/物流等垂直场景机器人；如果按“技术热度”看，VLA/机器人基础模型是当前最活跃方向；如果按“基础设施价值”看，数据采集、遥操作、仿真和合成数据是绕不开的底座。[2][5][6][3]
- 全球头部玩家主要集中在北美和中国，欧洲有 1X 等代表，但日本、韩国、拉美等区域在本次证据集中覆盖不足，说明“全球”更像是“北美+中国主导、欧洲补位”的格局。[1][2][7][8]

## 二、如何统一看待技术路线
我建议用一个更实用的四层分类，来消解“3 分法 vs 4 分法”的口径冲突：

1. 本体平台层：做人形、轮式、机械臂等硬件本体与运动控制。
2. 数据与训练层：真机遥操、动作采集、仿真、合成数据、训练场。
3. 机器人基础模型层：VLA、模仿学习、策略模型、多模态端到端控制。
4. 世界模型/空间生成层：3D 场景生成、空间理解、预测与规划。

这个分类的好处是：公司可以跨层布局，不必被单一标签限制；例如 Figure、AgiBot、NVIDIA、Google DeepMind 都同时触及多层，只是侧重点不同。[1][2][9][10][11][12][4]

## 三、各路线的成熟度判断

### 1）本体平台路线：最接近工程化，但通用性还不够
这条路线的核心是先把“身体”做出来，再逐步叠加智能。优点是工程路径清晰、容易做演示和行业试点；缺点是硬件成本高、可靠性要求高、通用能力弱，容易陷入“能跑会走但不好用”。[1][2]

代表公司：
- Figure AI：以人形机器人平台叠加 Helix VLA，目标是通用任务执行。产品已经公开到 Helix 这一代模型，并持续推进人形本体；商业化上更偏仓储/家庭/商业操作的早期验证，仍处试点和合作阶段。融资方面是 2024-2025 年最受关注的高融资公司之一；团队以 Brett Adcock 为核心，强项是机器人产品化和资本整合。[11]
- Apptronik：Apollo 是其主线产品，强调物流、制造等场景；2025 年与 Google DeepMind Robotics 的合作强化了“本体 + 基础模型”路径。商业化仍在试点/合作推进阶段，但已经进入明确的产业客户验证。融资为数亿美元级别的公开热度公司；团队来自 UT Austin 机器人研究积累。[13]
- Agility Robotics：Digit 是仓储/物流方向的代表，商业化进展相对更实；公开资料显示其已进入制造、仓储与物流部署，并有明确商业合作信号。融资和产能建设都围绕“交付能力”展开，团队长期深耕腿足机器人。[2]
- 1X：NEO Home Robot 代表家庭/服务场景路线，更强调“家用可用性”而非纯工业。产品已公开发布，商业化仍处非常早期，融资以战略资本和长期布局为主；团队带有欧洲机器人创业背景。[7]
- Sanctuary AI：Phoenix 与 Carbon 控制系统强调“通用工作机器人”，定位偏工业/企业。产品与演示进展较活跃，商业化仍以试点和展示为主；团队层面有 CTO 调整和公司更新，说明其正处于快速迭代阶段。[8][14]
- 中国阵营（智元机器人、宇树、优必选、傅利叶等）：整体以本体、运动控制、行业交付见长，正在叠加大模型、遥操和数据闭环。当前更多是“可交付本体 + 场景化应用”路线，商业化比纯基础模型更接近落地，但通用智能还在推进中。[1][2][3]

这条路线的阶段判断：工程化最成熟，商业化最先跑出来，但“通用性”仍是最大短板。[1][2]

### 2）VLA / 机器人基础模型路线：当前最热，但还在验证期
这条路线试图把视觉、语言、动作统一到一个策略模型里，让机器人通过自然语言和多模态输入直接学会任务。优点是泛化潜力大、能跨任务迁移；缺点是数据需求极高，安全性、实时性和长尾任务仍难。[9][10][11][5][15][6][16][12]

代表公司/项目：
- Google DeepMind：Gemini Robotics 1.5 明确把“AI agent 带入物理世界”，说明大厂在把通用多模态模型向机器人控制延伸。产品进度已经从研究走向模型发布；商业化更多体现在平台/合作伙伴生态，而不是直接卖机器人本体。[17][9]
- NVIDIA：Isaac GR00T N1 是开放式人形机器人基础模型，核心是给整个生态提供训练和部署底座。商业化上 NVIDIA 更像“卖铲子”，靠芯片、软件栈和平台能力变现，本身不做终端机器人交付。[10]
- Figure AI：Helix 是典型的 VLA 方向，强调通用人形操作能力。它把“人形本体”和“基础模型”深度绑定，是当前最受关注的样板之一。[11]
- Physical Intelligence：π0 是面向通用机器人控制的基础模型代表，偏 manipulation-first。产品更像研究驱动的通用策略模型，还未进入大规模终端商业化，但在技术路线层面影响力很强。[5][15]
- Covariant：RFM-1 主要面向仓储机器人推理与操作，属于“垂直场景 VLA/基础模型”。商业化更贴近仓储和物流，因此比纯通用机器人更容易验证价值。[6]
- OpenVLA：开源路线，价值在于建立通用基线和生态，产品化不是其主诉求，但对行业研究和二次开发意义很大。[16]
- AgiBot：GO-1 从 VLA 进一步走向 ViLLA，说明中国公司也在尝试把基础模型和本体闭环打通。它的特点是“研究 + 产品”并行，既做模型也做机器人平台。[12][18]

这条路线的阶段判断：技术前沿、热度最高，但仍处于“模型能力快速上升、商业闭环尚未稳定”的阶段。[17][10][11][5][16][12]

### 3）数据采集 / 远程操控 / 仿真训练路线：最关键的底座
具身智能的瓶颈不是只靠更大的模型，而是高质量动作数据太少、太贵、太慢。因此数据采集、遥操作、仿真和合成数据是整个行业的“隐形主线”。[3][4]

代表性方向与公司：
- NVIDIA：除了 GR00T，也在推动世界模型/合成数据能力，属于“算力 + 仿真 + 训练工具”一体化供给方。[10]
- 群核科技：公开资料中其 SpatialLM / SpatialVerse 被视为“空间数据/合成数据”代表，强调从空间理解和 3D 数据生成支撑机器人训练。[4]
- Figure / 1X / Apptronik / AgiBot：这些公司都在不同程度上构建遥操作、数据采集和本体交互闭环，虽然对外宣传重点不同，但底层都离不开数据引擎。[11][12][7][13]
- 训练场/数据工厂：2025 年行业白皮书提到北京、上海等地加快建设具身智能数据采集训练场，说明“数据基础设施”已从概念变成产业建设。[3]

这条路线的阶段判断：作为基础设施最成熟、最确定；作为独立商业模式还在成型，但战略价值很高。[3][4]

### 4）世界模型 / 空间生成路线：最前沿，但仍偏研究
世界模型试图让机器人先“想象”物理世界，再做决策。它的目标不是单次动作，而是对环境、后果和长期规划做预测。优点是有望提升长程规划和泛化；缺点是物理一致性、语义结构、数据规模和评估标准都还不成熟。[1][4]

代表性信号：
- Google DeepMind 的相关工作、NVIDIA 的 Cosmos/世界模型思路，以及李飞飞相关研究都在推动这一方向。
- 量子位文章对“合成重建 vs 全端生成”做了很好的拆解，说明空间数据本身也在快速演化，行业还没有统一最优解。[4]

这条路线的阶段判断：离大规模商业化最远，但长期潜力大，可能成为下一阶段具身智能的“认知层”。[1][4]

## 四、代表公司速览
下面按“路线 + 公司”给一个更实用的归类。

### A. 机器人基础模型 / VLA
- Figure AI：Helix；人形+VLA 深度绑定；商业化偏仓储/家庭早期验证；融资热度极高；团队以 Brett Adcock 为核心。[11]
- Google DeepMind：Gemini Robotics 1.5；偏平台和生态；商业化通过合作伙伴放大。[17][9]
- NVIDIA：Isaac GR00T N1；基础设施和工具链；商业化靠平台。[10]
- Physical Intelligence：π0；通用控制模型；仍偏研究与早期产品化。[5][15]
- Covariant：RFM-1；仓储机器人推理；商业化贴近物流场景。[6]
- OpenVLA：开源基线；生态价值大于直接商业化。[16]
- AgiBot：GO-1 / ViLLA；国内少数同时做模型与本体的玩家。[12][18]

### B. 人形/通用机器人平台
- Apptronik：Apollo；制造/物流试点较明确；与 DeepMind 合作增强模型能力。[13]
- Agility Robotics：Digit；仓储/物流商业化进展更快。[2]
- 1X：NEO Home Robot；家庭场景方向，仍早期。[7]
- Sanctuary AI：Phoenix；工业/企业工作机器人；产品和团队都在快速迭代。[8][14]
- 中国公司：智元、宇树、优必选、傅利叶等；本体与场景交付较强，正向具身大模型叠加。[1][2][3]

### C. 数据/仿真/空间生成
- NVIDIA：训练、仿真、世界模型工具链最完整。[10]
- 群核科技：SpatialLM / SpatialVerse 是空间数据路线的代表。[4]
- 训练场与数据工厂：北京/上海等地的产业化基础设施在加速成形。[3]

## 五、各路线的优缺点
- 本体平台路线优点是“能卖、能演示、能落地”；缺点是硬件贵、维护难、通用性弱。[1][2]
- VLA/基础模型路线优点是“泛化潜力最大”；缺点是数据稀缺、实时控制难、安全验证难。[9][10][5][16]
- 数据/仿真路线优点是“决定上限且可规模化”；缺点是 sim2real gap 仍然明显，数据质量比数量更重要。[3][4]
- 世界模型路线优点是“可能解决长时序规划”；缺点是离产品化最远，仍以研究为主。[1][4]

## 六、当前发展阶段判断
- 最成熟：仓储、物流、工业搬运、简单抓取等垂直场景机器人。[2][6][13]
- 正在放量：人形机器人平台 + 任务模型的试点阶段，开始出现明确合作客户和演示闭环。[11][7][8]
- 最热研发前沿：VLA / 机器人基础模型。[17][10][5][16][12]
- 最长期的底层方向：世界模型、空间生成、合成数据闭环。[3][4]

## 七、你在看全球具身智能时，最该关注的 5 个指标
- 是否有稳定的数据闭环，而不是只会做 demo。[3][4]
- 是否能跨任务泛化，而不是单一场景脚本化执行。[9][5][16]
- 是否已经进入真实客户试点，而不是停留在发布会。[2][13][8]
- 是否具备可持续融资和人才吸引力。[11][15][7][14]
- 是否在“本体、数据、模型、世界模型”四层中占住至少两层。[1][2][10][12]

## 八、局限说明
- 本次证据集对北美和中国覆盖较强，对欧洲、日本、韩国等区域覆盖不足，因此“全球”维度仍偏头部样本主导。[1][2]
- 部分公司融资金额、交付数量、客户名称在公开证据中并不统一，我在上面尽量用“阶段性、方向性”表述，避免把不一致数据写死。
- 具身智能路线仍在快速变化，今天看起来是“VLA + 人形 + 数据工厂”的组合，未来也可能被更强的世界模型或更成熟的垂直产品路径重写。[1][3][4]

## 参考资料
[1] [PDF] 具身智能发展报告 - 中国信息通信研究院
http://www.caict.ac.cn/kxyj/qwfb/bps/202601/P020260130541978285206.pdf

[2] [PDF] 具身智能发展报告 - 北京人形机器人创新中心
https://x-humanoid.com/storage/website/2025/01-14/6785fd2145c36-1-27438.pdf

[17] The latest AI news we announced in March - Google Blog
https://blog.google/innovation-and-ai/products/google-ai-updates-march-2025/

[9] Gemini Robotics 1.5 を発表、AI エージェントを物理世界に
https://blog.google/intl/ja-jp/company-news/technology/gemini-robotics-15-ai/

[10] NVIDIA Isaac GR00T N1: An Open Foundation Model for Humanoid Robots
https://research.nvidia.com/publication/2025-03_nvidia-isaac-gr00t-n1-open-foundation-model-humanoid-robots

[11] Helix: A Vision-Language-Action Model for Generalist Humanoid Robots
https://www.figure.ai/news/helix

[5] Vision-Language-Action Models for General Robot Control
https://huggingface.co/blog/pi0

[15] Physical Intelligence (π)
https://www.pi.website/

[6] Covariant introduces RFM-1 to give robots the human-like ability to reason
https://covariant.ai/covariant-introduces-rfm-1-to-give-robots-the-human-like-ability-to-reason/

[16] OpenVLA: An Open-Source Vision-Language-Action Model
https://arxiv.org/abs/2406.09246

[12] AgiBot GO-1: The Evolution of Generalist Embodied Foundation Model from VLA to ViLLA
https://agibot-world.com/blog/go1

[18] AgiBot Research
https://www.agibot.com/research

[7] NEO Home Robot
https://www.1x.tech/neo

[13] Apptronik Partners with Google DeepMind Robotics
https://apptronik.com/news-collection/apptronik-partners-with-google-deepmind-robotics

[8] Sanctuary AI Unveils Phoenix™ - A Humanoid General-Purpose Robot Designed for Work
https://sanctuary.ai/news/sanctuary-ai-unveils-phoenix-a-humanoid-general-purpose-robot-designed-for-work/

[14] Company and Team Update - Sanctuary AI
https://www.sanctuary.ai/blog/company-and-team-update

[3] 2025商用具身智能白皮书
https://pdf.dfcfw.com/pdf/H3_AP202512031793353788_1.pdf?1764833841000.pdf=

[4] 具身空间数据技术的路线之争：合成重建VS全端生成 – 量子位
https://www.qbitai.com/2025/04/275178.html

如果你愿意，我下一步可以把这份内容再整理成一个更适合汇报用的版本：一页结论版，或者做成“公司/路线/融资/进度”的对照表。

## 参考文献

[1] 具身智能发展报告（2025年） http://www.caict.ac.cn/kxyj/qwfb/bps/202601/P020260130541978285206.pdf

[2] 770亿美元市场引爆：中国具身智能机器人从“秀肌肉”到“真干活” https://my.idc.com/getdoc.jsp?containerId=prCHC54010625

[3] NVIDIA Isaac GR00T N1: An Open Foundation Model for Humanoid ... https://research.nvidia.com/publication/2025-03_nvidia-isaac-gr00t-n1-open-foundation-model-humanoid-robots

[4] Helix: A Vision-Language-Action Model for Generalist Humanoid ... https://www.figure.ai/news/helix

[5] [PDF] 具身智能发展报告 - 北京人形机器人创新中心 https://x-humanoid.com/storage/website/2025/01-14/6785fd2145c36-1-27438.pdf

[6] IDC首次发布全球具身智能机器人创新者榜单 https://my.idc.com/getdoc.jsp?containerId=prCHC53968025&_gl=1*134izcj*_ga*MTg0OTg4MTY1MC4xNzUzOTQ4NDYx*_ga_541ENG1F9X*czE3NjQ3NTE2ODEkbzk4JGcxJHQxNzY0NzUxOTI1JGoyMSRsMCRoMA..*_gcl_au*OTk3Njc2OTQyLjE3NjE3MjQ3MjE.

[7] [PDF] 甲子光年智库...具身智能技术发展与行业应用简析 https://download.s21i.co99.net/28254755/0/0/ABUIABA9GAAgmcKqvQYomLfimwU.pdf?f=2025%E5%85%B7%E8%BA%AB%E6%99%BA%E8%83%BD%E8%A1%8C%E4%B8%9A%E5%8F%91%E5%B1%95%E7%A0%94%E7%A9%B6%E6%8A%A5%E5%91%8A%E5%85%B7%E8%BA%AB%E6%99%BA%E8%83%BD%E6%8A%80%E6%9C%AF%E5%8F%91%E5%B1%95%E4%B8%8E%E8%A1%8C%E4%B8%9A%E5%BA%94%E7%94%A8%E7%AE%80%E6%9E%90.pdf&v=1739235609

[8] The latest AI news we announced in March - Google Blog https://blog.google/innovation-and-ai/products/google-ai-updates-march-2025/

[9] 具身智能产业深度研究（五）：人形机器人硬实力助力行业加速量产 https://www.fxbaogao.com/detail/5129181

[10] 竞合共进 规范先行：全球具身智能的发展与治理 https://news.gmw.cn/2026-03/19/content_38656011.htm

[11] 2025年，人形机器人走到哪一步了？｜机器人系列｜具身智能年度盘点 https://www.youtube.com/watch?v=qs0ovkaacls

[12] [PDF] 计算机行业深度报告大脑：具身智能落地的关键 https://pdf.dfcfw.com/pdf/H3_AP202510241768086302_1.pdf?1761314712000.pdf

[13] [PDF] 具身智能科技前沿热点 https://aigc.idigital.com.cn/djyanbao/%E3%80%90%E4%B8%AD%E5%85%B3%E6%9D%91%E6%99%BA%E5%8F%8B%E7%A0%94%E7%A9%B6%E9%99%A2%E3%80%912024%E5%85%B7%E8%BA%AB%E6%99%BA%E8%83%BD%E7%A7%91%E6%8A%80%E5%89%8D%E6%B2%BF%E7%83%AD%E7%82%B9-2025-01-02.pdf

[14] Gemini Robotics 1.5 を発表、AI エージェントを物理世界に https://blog.google/intl/ja-jp/company-news/technology/gemini-robotics-15-ai/

[15] [PDF] 具身智能：万亿赛道，落地元年 https://pdf.dfcfw.com/pdf/H3_AP202503101644227280_1.pdf

[16] 2025年具身智能行业研究跨领域融合引领的新一轮智能革命 https://www.fxbaogao.com/detail/5044556

[17] 2025商用具身智能白皮书 https://pdf.dfcfw.com/pdf/H3_AP202512031793353788_1.pdf?1764833841000.pdf

[18] 具身智能发展趋势与展望 - Engineering https://www.engineering.org.cn/sscae/CN/10.15302/J-SSCAE-2025.07.019
