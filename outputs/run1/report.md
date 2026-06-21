## 一、先给结论

全球具身智能目前不是单一路线竞争，而是“终端形态 + 基础模型 + 数据/训练基础设施”三层叠加。最接近商业化的，不是“通用家用人形机器人”，而是仓储/工厂/巡检等明确场景下的轮式移动操作机器人和四足/腿式机器人；人形机器人仍是最受资本关注、但工程难度和兑现周期也最长的路线 [1][2][3][4][5][6][7][8][9][10]。

如果按商业成熟度粗排：
1. 四足/腿式、轮式移动操作：已经有较明确的客户部署和产品收入路径。
2. 人形机器人：已进入样机、试点、少量产线导入阶段，但离大规模盈利还早。
3. 机器人基础模型/VLA：更像“放大器”和平台能力，短期多由整机公司内化，而不是独立卖模型。
4. 远程操作、仿真、数据采集：是所有路线的底座，但独立公司在本次证据里相对不足，且商业形态更隐蔽。

## 二、全球具身智能的主要技术路线

| 路线 | 典型形态 | 主要落地场景 | 当前成熟度 |
|---|---|---|---|
| 人形机器人 | 双足、双臂、类人躯干 | 制造、物流、通用操作、家庭 | 早期到试点 |
| 轮式移动操作机器人 | 移动底盘 + 机械臂 | 仓储、配送、零售、医院 | 相对更成熟 |
| 四足/腿式机器人 | 四足/多足/腿式平台 | 巡检、安防、能源、灾害环境 | 已有明确商用 |
| 机器人基础模型 / VLA | 多模态感知 + 动作生成 | 通用操作能力底座 | 仍在快速演进 |
| 远程操作 / 仿真 / 数据采集 | teleop、仿真训练、合成数据 | 训练与评测基础设施 | 底层关键能力 |

## 三、各路线的代表性公司

### 1）人形机器人路线

- Figure：最典型的“人形 + VLA + 场景落地”代表之一，已经推进到 BMW 产线生产/测试场景，且完成 Series C 融资；创始人 Brett Adcock 是典型连续创业者，团队偏“高速产品化 + 大模型叙事” [11][12][13]。
- Apptronik：以 Apollo 为核心，技术路线强调面向工业和商业场景的人形平台，已与 Mercedes-Benz 达成商业合作；融资上完成了超 9.35 亿美元的 Series A，团队与 UT Austin 机器人学派联系紧密 [14][15][16]。
- Agility Robotics：Digit 是人形路线里最接近仓储商业化的产品之一，公开材料显示已在仓储作业中搬运超过 10 万个 tote；公司完成过 1.5 亿美元 Series B，团队根基来自 Oregon State University 的腿式机器人研究传统 [9][17][18]。
- 1X：NEO Home Robot 明确指向家庭场景，商业上仍偏早期，但已拿到 1 亿美元 Series B；路线特点是“面向家庭/服务业的通用人形 + AI 数据闭环” [19][20][21]。
- Tesla：Optimus 属于“内部优先”的人形路线，公开信息更偏 AI & Robotics 总体战略，商业化尚未对外展开；优势在于制造、供应链和数据规模，而不是先发产品 [22]。
- Boston Dynamics（Atlas）：Atlas 代表前沿能力展示，商业化仍偏研发；但 Boston Dynamics 整体在类人/类足/移动操作三线并行，且已被 Hyundai 控股，Atlas 更像技术前沿标杆而非当前收入引擎 [23][24][25]。

### 2）轮式移动操作机器人路线

- Boston Dynamics Stretch：这是仓储移动操作的标杆，Stretch 已对外开放商用采购，2025 年又与 DHL 推进仓储自动化合作；这条线的特点是“先解决搬运/拣选/箱体作业”，比通用人形更容易形成付费客户 [1][2][3]。
- Collaborative Robotics：Proxie 定位于真实世界的协作型移动机器人，主打在工厂/仓储环境中执行搬运与操作；公司完成 1 亿美元 Series B，创始人 Brad Porter 具有 Amazon Robotics 背景，商业化路径很典型：从明确场景切入 [4][26][27]。
- Brightpick：以 Autopicker 为代表，把移动操作做成仓库柔性系统，已有客户部署案例；最新公开融资信息显示其曾融资 1,200 万美元，整体处于“产品已成型、商业化在推进”的阶段 [5][28][29][30]。
- RoboForce：Titan 面向真实工业部署，公开材料强调“real-world industrial deployment”，并披露总融资约 1,500 万美元；它代表的是工业移动操作/重载作业方向，仍属早期创业公司阶段 [6][31][32]。
- Pal Robotics：TIAGO Pro、MANOLO、PRO-CARED 等项目显示其更偏欧洲服务机器人与系统集成路线，产品和项目都比较扎实，但商业化形态更分散，偏工程化交付 [33][34][35][36]。
- Robotnik：RB-KAIROS 2 是典型的移动操作平台，且已被 United Robotics Group 收购；它更像“商用底盘/平台供应商”，在欧洲自动化生态里位置清晰 [8][37][38][39]。

### 3）四足/腿式机器人路线

- Boston Dynamics（Spot）：Spot 是最成熟的商用四足平台之一，面向工业巡检、能源、安防等场景；Boston Dynamics 的四足路线已经从“技术展示”变成“行业产品” [23][40][25]。
- ANYbotics：ANYmal X 是首个防爆腿式机器人之一，强调工业巡检和高危环境；公司还披露了额外 6,000 万美元融资，说明它的商业化和产业化路径很清楚 [10][41][42]。
- Ghost Robotics：Vision 60 代表军警/防务和高机动巡检方向，产品化程度不低，但公开融资和团队信息相对不透明，商业化主要集中在特种应用 [43][44]。
- DEEP Robotics：典型的中国腿式机器人公司，公开资料显示其在产品和行业应用上持续推进，创始人 Zhu Qiuguo 也在世界经济论坛等平台曝光；整体更偏工业巡检、安防、应急场景 [45][46][47]。
- Unitree：以低成本、高性能平台著称，在四足和人形上都很活跃；公开披露更多集中在产品而非融资细节，商业上通常被视为“规模化硬件制造能力强”的代表 [48]。

### 4）机器人基础模型 / VLA 路线

这条路线在现实里通常不是“单独卖模型”，而是被整机公司内化成控制中枢。公开证据里最典型的代表是：

- Figure：把人形硬件、视觉语言动作能力和场景部署合成一个闭环，是 VLA 最直观的商业化载体之一 [11][12][13]。
- Tesla：依托海量视觉与制造数据，走的是“车端/工厂端数据反哺机器人控制”的路线，核心不是先卖模型，而是自建数据飞轮 [22]。
- 1X：NEO 更偏家庭场景，强调人机交互和数据积累，路线本质上也是“硬件 + 数据 + 模型”一体化 [19][20][21]。
- Apptronik：虽然主打整机，但其商业合作和平台化思路，也体现了模型能力正在被嵌入机器人系统，而不是单独售卖 [14][15][16]。

这一路线的关键判断是：短期内“模型能力”不会以独立 SaaS 的形式大规模变现，更可能沉到硬件公司内部，成为效率和泛化能力的核心壁垒。

### 5）远程操作 / 仿真训练 / 数据采集路线

本次收集到的公开证据里，专门做这一层的独立公司样本不够完整，所以不适合硬编“代表公司名单”。但从行业结构看，这一层非常关键，原因有三点：

- 机器人没有足够真实数据时，遥操作和仿真几乎是训练通用策略的前提。
- 远程操作是“先卖服务再积累数据”的常见商业化起点。
- 仿真与合成数据会决定后续 VLA、强化学习和安全评测的上限。

简单说：这层不是最吸睛的，但几乎是所有前台路线的基础设施。

## 四、融资、产品与商业化的总体格局

- 大额资本最集中在“人形 + 基础模型”叙事上，代表公司包括 Apptronik、Figure、Agility、1X 等 [18][11][15][19]。
- 已经产生较明确客户价值的，更多是仓储移动操作和工业巡检：比如 Stretch、Digit、ANYmal X、Spot [1][2][17][41][42]。
- 纯演示型的人形机器人仍然很多，但真正能进入客户流程、形成采购合同或试点合同的公司更少；商业化兑现速度明显慢于融资速度 [12][14]。
- 中国公司在低成本制造、工程化和产品落地上更强，欧美公司在基础研究、资本吸引力和大客户试点上更强；这两种优势正在分化而非简单重叠 [48][45][47]。

## 五、团队画像

从团队结构看，具身智能头部公司大致有四类来源：

- 学术派：从机器人实验室、大学 spinout 出来，如 Apptronik、ANYbotics、Agility 的核心技术背景都很强 [18][16][10]。
- 大厂派：来自 Amazon Robotics、Tesla 等工业化环境，代表 Collaborative Robotics、Tesla [26][22]。
- 连续创业派：Figure 的 Brett Adcock 是典型样本 [13]。
- 工程制造派：如 Unitree、DEEP Robotics、Robotnik 这类更重产品和供应链能力的公司 [39][48][45][47]。

## 六、我的判断：未来 12-24 个月最值得看的方向

1. 最先规模化赚钱的，仍大概率是“轮式移动操作 + 工业巡检”。
2. 人形机器人会继续拿走最多融资和媒体注意力，但短期更可能是“单场景人形工人”而不是通用家庭管家。
3. VLA 会成为机器人公司的必选项，但最强的玩家往往不是纯模型公司，而是能把模型、数据和硬件闭环起来的整机公司。
4. 具身智能的竞争，最后会回到三个问题：谁有真实数据、谁能量产、谁能在明确场景里持续交付。
5. 未来的赢家未必是“外形最像人”的公司，而是“最早把机器人变成可重复交付生产力工具”的公司。

## 七、信息局限

- 本报告基于已收集到的公开网页、新闻稿和公司介绍，融资金额、团队构成和商业化进度有些只披露到轮次或合作层面，未必完整可比 [1]-[21]。
- 对于部分公司，公开资料更偏宣传口径，缺少统一口径的营收、出货量和客户留存数据。
- 远程操作、仿真训练、数据采集这类底层路线，在公开市场上往往以“内部能力”存在，独立公司样本不足，因此只做趋势判断，不强行列出不充分的代表公司。

如果你要，我下一步可以把这份报告再整理成一页版表格，方便直接放进 PPT 或内部汇报。

## 参考文献

[1] https://bostondynamics.com/products/stretch/

[2] https://bostondynamics.com/news/boston-dynamics-stretch-robot-now-available-for-commercial-purchase/

[3] https://group.dhl.com/en/media-relations/press-releases/2025/dhl-group-signs-mou-with-boston-dynamics-and-accelerates-cross-business-automation-strategy.html

[4] https://www.prnewswire.com/news-releases/collaborative-robotics-raises-100-million-in-series-b-funding-302112670.html

[5] https://brightpick.ai/brightpick-raises-12-million/

[6] https://www.prnewswire.com/news-releases/roboforce-introduces-ai-robot-titan-for-real-world-industrial-deployment-and-announces-15m-in-total-funding-302458546.html

[7] https://www.rainbow-robotics.com/en_pr/20240405

[8] https://robotnik.eu/products/mobile-robots/rb-kairos-2/

[9] Company | Agility Robotics https://agilityrobotics.com/company

[10] Company | ANYbotics https://anybotics.com/about-us/company

[11] Series C https://figure.ai/news/series-c

[12] Production at BMW https://figure.ai/news/production-at-bmw

[13] Bio https://brettadcock.com/bio

[14] Apptronik and Mercedes-Benz Enter Commercial Agreement https://apptronik.com/news-collection/apptronik-and-mercedes-benz-enter-commercial-agreement

[15] Apptronik Closes Over $935 Million Series A https://apptronik.com/news-collection/apptronik-closes-over-935-million-series-a

[16] Leadership https://apptronik.com/leadership

[17] Digit Moves Over 100k Totes https://agilityrobotics.com/content/digit-moves-over-100k-totes

[18] Agility Robotics Raises $150M Series B Led by DCVC and Playground Global https://agilityrobotics.com/content/agility-robotics-raises-150m-series-b-led-by-dcvc-and-playground-global

[19] 1X Secures $100M in Series B Funding https://1x.tech/discover/1x-secures-100m-in-series-b-funding

[20] NEO Home Robot https://1x.tech/discover/neo-home-robot

[21] 1X https://1x.tech

[22] AI & Robotics https://tesla.com/AI

[23] About | Boston Dynamics https://bostondynamics.com/about

[24] Atlas https://bostondynamics.com/products/atlas

[25] Hyundai Motor Group Completes Acquisition of Boston Dynamics from SoftBank https://bostondynamics.com/news/hyundai-motor-group-completes-acquisition-of-boston-dynamics-from-softbank

[26] https://www.co.bot/story

[27] https://www.prnewswire.com/news-releases/introducing-proxie-cobots-collaborative-robot-built-for-the-real-world-302311699.html

[28] https://brightpick.ai/about-us/

[29] https://www.therobotreport.com/rbr50-spotlight-brightpick-autopicker-applies-mobile-manipulation-ai-for-warehouse-flexibility/

[30] https://brightpick.ai/superior-communications-to-deploy-brightpick/

[31] https://www.businessinsider.com/roboforce-deck-10-million-robotic-workforce-2025-1

[32] https://www.roboforce.ai/news/wef-annual-meeting-of-the-new-champions

[33] https://pal-robotics.com/robot/tiago-pro/

[34] https://pal-robotics.com/who-we-are/

[35] https://pal-robotics.com/projects/manolo/

[36] https://pal-robotics.com/projects/pro-cared/

[37] https://video.universal-robots.com/robotnik-rb-kairos

[38] https://www.crunchbase.com/organization/robotnik

[39] https://robotnik.eu/united-robotics-group-gmbh-strengthens-ecosystem-of-european-robotics-leaders-with-the-acquisition-of-robotnik-automation-s-l-l/

[40] Spot https://bostondynamics.com/products/spot

[41] ANYbotics Raises Additional $60 Million to Drive U.S. Expansion https://anybotics.com/news/anybotics-raises-additional-60-million-to-drive-u-s-expansion

[42] ANYmal X: The World's First Ex-Proof Legged Robot https://anybotics.com/news/anymal-x-the-worlds-first-ex-proof-legged-robot

[43] About Us https://ghostrobotics.io/about-us

[44] Vision 60 https://ghostrobotics.io/vision-60

[45] DEEP Robotics https://deeprobotics.cn/en

[46] https://deeprobotics.cn/en/wap/article/id/252.html

[47] People: Zhu Qiuguo https://weforum.org/people/zhu-qiuguo

[48] Unitree Robotics https://unitree.com
