# 排除 Wikipedia 后的搜索测试报告

**生成时间**: 2026-08-04 13:40:47
**测试目的**: 模拟 GraphResearcher 真实搜索环境（排除 Wikipedia），对比不同查询策略

---

## 核心问题

GraphResearcher 在 WLC-bench 测试中**必须排除 Wikipedia**（`-site:en.wikipedia.org`），
这是反作弊要求。因此系统需要从**其他来源**获取 Ring of Nestor 的信息。

---

## 测试结果对比

| 查询 | 返回数 | 相关数 | 最佳来源 | 最佳 Score |
|------|--------|--------|----------|-----------|
| V1_no_wiki | 5 | 5 | Catalog Record: ʻThe ring of N | 0.796 |
| V2_no_wiki | 5 | 3 | Sir Arthur Evans: Gifts to the | 0.798 |
| V3_no_wiki | 5 | 5 | The Ring of Nestor: a Glimpse  | 0.825 |
| V4_graphresearcher_style | 5 | 2 | (2020) A. G. Vlachopoulos, “Th | 0.683 |
| V5_v7_style | 5 | 2 | some observations on the icono | 0.624 |

---

## 详细结果

### V1_no_wiki

**查询**: `Ring of Nestor -site:en.wikipedia.org`

**描述**: 最简洁查询 + 排除 Wikipedia

✅ **1. Catalog Record: ʻThe ring of Nestor;̓ a glimpse into the Minoan after-world, and a sepulchral treasure of gold signet-rings and bead-seals from Thisbê, Boeotia**
- URL: https://catalog.hathitrust.org/Record/000609034
- Score: 0.7964
- 预览: by Sir Arthur Evans. With five plates, one coloured and four collotype, and fifty-four figures in the text.  ## Description  ### Tools  Cite thisExpor...

✅ **2. SOME OBSERVATIONS ON THE ICONOGRAPHY OF THE ‘RING OF NESTOR’**
- URL: https://www.academia.edu/83658257/SOME_OBSERVATIONS_ON_THE_ICONOGRAPHY_OF_THE_RING_OF_NESTOR_
- Score: 0.7434
- 预览: This paper presents a rare bronze finger ring that was found more than half a century ago and bears a symbol known mainly from the coins of Mattathias...

✅ **3. The Ring of Nestor: a Glimpse into the Minoan After-World and a Sepulchral Treasure of Gold Signet-Rings and Bead-Seals from Thisbe, Boeotia | Nature**
- URL: https://www.nature.com/articles/116635a0
- Score: 0.6975
- 预览: CHILDE, V. The Ring of Nestor: a Glimpse into the Minoan After-World and a Sepulchral Treasure of Gold Signet-Rings and Bead-Seals from Thisbe, Boeoti...

✅ **4. The Pseudo-Minoan Nestor Ring and Its Egyptian Iconography |
Journal of Ancient Egyptian Interconnections**
- URL: https://journals.librarypublishing.arizona.edu/jaei/article/id/960
- Score: 0.6902
- 预览: The so-called Nestor Ring was found in 1924 and was accepted as authentic by Sir Arthur Evans whereas many other scholars condemned it as a forgery. I...

✅ **5. "The ring of Nestor". A glimpse into the Minoan after-world and a sepulchral treasure of gold signet-rings and bead-seals from Thisbê, Boeotia**
- URL: https://digi.ub.uni-heidelberg.de/diglit/evans1925?ui_lang=eng
- Score: 0.6766
- 预览: Heidelberg historic literature – digitized  Image 1: Universitätsbibliothek HeidelbergImage 2: Universitätsbibliothek Heidelberg  1.   Homepage 2.   D...

### V2_no_wiki

**查询**: `Ring of Nestor Arthur Evans Ashmolean Museum -site:en.wikipedia.org`

**描述**: 精准标识符 + 排除 Wikipedia

✅ **1. Sir Arthur Evans: Gifts to the Ashmolean Museum | Nature**
- URL: https://www.nature.com/articles/143235b0
- Score: 0.7979
- 预览: cylinders and ring bezels in steatite, cornelian, ivory and other materials, engraved with pictographs, scenes of ritual, bullfighting and other sport...

✅ **2. some observations on the iconography of the 'ring of nestor'**
- URL: https://www.academia.edu/83658257/SOME_OBSERVATIONS_ON_THE_ICONOGRAPHY_OF_THE_RING_OF_NESTOR_
- Score: 0.6499
- 预览: The so-called Nestor Ring was found in 1924 and was accepted as authentic by Sir Arthur Evans whereas many other scholars condemned it as a forgery. I...

✅ **3. Ring of Nestor - A... - Archaeology and Ancient World**
- URL: https://www.facebook.com/ArchaeologyandAncientWorld9/posts/ring-of-nestor-a-3700-year-old-gold-signet-ring-from-crete-late-minoan-period-c-/1401558432013893
- Score: 0.3887
- 预览: '/%3E%3Cpath d='M16.0001 7.9996c0 4.418-3.5815 7.9996-7.9995 7.9996S.001 12.4176.001 7.9996 3.5825 0 8.0006 0C12.4186 0 16 3.5815 16 7.9996Z' fill='ur...

❌ **4. [PDF] THE MINOAN WORLD - Aegeus Society**
- URL: https://www.aegeussociety.org/wp-content/uploads/2022/03/Evans-1936-Minoan-World.pdf
- Score: 0.3323
- 预览: have contained the remains upside down. In the exhibition of the ‘Treasure’ this is well shown by the electrotypes presenting the backs of the objects...

❌ **5. The Pseudo Minoan Nestor Ring and Its Eg | PDF**
- URL: https://www.scribd.com/document/869354154/The-Pseudo-Minoan-Nestor-Ring-and-Its-Eg
- Score: 0.2947
- 预览: Scribd - Download on the App Store Scribd - Get it on Google Play [...] Scribd  # The Pseudo Minoan Nestor Ring and Its Eg  The Pseudo Minoan Nestor R...

### V3_no_wiki

**查询**: `Ring of Nestor gold signet ring Arthur Evans 1925 -site:en.wikipedia.org`

**描述**: 具体年份+标识符 + 排除 Wikipedia

✅ **1. The Ring of Nestor: a Glimpse into the Minoan After-World ...**
- URL: https://www.nature.com/articles/116635a0
- Score: 0.8249
- 预览: The Ring of Nestor: a Glimpse into the Minoan After-World and a Sepulchral Treasure of Gold Signet-Rings and Bead-Seals from Thisbe, Boeotia.  By Sir ...

✅ **2. Catalog Record: ʻThe ring of Nestor;̓ a glimpse into the...**
- URL: https://catalog.hathitrust.org/Record/000609034
- Score: 0.7116
- 预览: by Sir Arthur Evans. With five plates, one coloured and four collotype, and fifty-four figures in the text.  ## Description  ### Tools  Cite thisExpor...

✅ **3. ʻThe Ring of Nestor;̓: A Glimpse Into the Minoan After-world ...**
- URL: https://books.google.com/books/about/%CA%BBThe_Ring_of_Nestor_%CC%93.html?id=c9waAAAAYAAJ
- Score: 0.5872
- 预览: Author, Sir Arthur Evans ; Publisher, Macmillan and Company, Limited, 1925 ; Original from, the University of Virginia ; Digitized, May 15, 2008 ; Len...

✅ **4. Ring of Nestor: 3700-year-old gold signet ring from Crete**
- URL: https://www.facebook.com/groups/archeologyandcivilizations/posts/26471243725875801
- Score: 0.5861
- 预览: Ring of Nestor - A ~3700-year-old gold signet ring from Crete, Late Minoan Period, (c. 1700-1450 BCE), now housed at the Ashmolean Museum in Oxford....

✅ **5. Evans, Arthur J.: "The ring of Nestor". A glimpse into the ...**
- URL: https://digi.ub.uni-heidelberg.de/diglit/evans1925?ui_lang=eng
- Score: 0.5436
- 预览: Page  Full text search  Information about full text search/OCR  ## Content     Titelblatt    1-42 I. Sepulchral treasure of gold signet-rings and bead...

### V4_graphresearcher_style

**查询**: `Ring of Nestor Mycenaean gold ring archaeological study museum collection scholarly publication provenance iconography dating -site:en.wikipedia.org`

**描述**: GraphResearcher V8 的实际查询（过于冗长）

✅ **1. (2020) A. G. Vlachopoulos, “The Ring of Nestor and the quest for authenticity”, in F. Blakolmer (ed.) Current Approaches and New Perspectives in Aegean Iconography, Aegis 18 (2020), pp. 223-252.**
- URL: https://www.academia.edu/43416584/_2020_A_G_Vlachopoulos_The_Ring_of_Nestor_and_the_quest_for_authenticity_in_F_Blakolmer_ed_Current_Approaches_and_New_Perspectives_in_Aegean_Iconography_Aegis_18_2020_pp_223_252
- Score: 0.6832
- 预览: Image 18: Academia  580 California St., Suite 400  San Francisco, CA, 94104  © 2026 Academia. All rights reserved [...] 51.   Marinatos & Jackson 2011...

❌ **2. Nestor - Home**
- URL: https://classics.uc.edu/nestor
- Score: 0.5706
- 预览: J. Czebreszuk, K. Nikolentzos, K. Kostanti, I. Sobkowiak-Tabaka, J. Proch, M. Kontaki, P. Lazaris, and T. Zygouris, “Archaeometric Analysis of Mycenae...

❌ **3. Pylos of Nestor A Mycenaean Kingdom Revealed - National Archaeological Museum**
- URL: https://www.namuseum.gr/en/temporary_exhibition/pylos-of-nestor-a-mycenaean-kingdom-revealed
- Score: 0.4822
- 预览: Exhibition Opening: 25 May 2026  Exhibition Period: 26 May – 31 October 2026  Opening Hours:   Wednesday to Monday: 08:00–20:00 / last admission at 19...

❌ **4. Instagram**
- URL: https://www.instagram.com/p/DYxsmt0jiGw
- Score: 0.3405
- 预览: ➡️ The narrative of the exhibition is a journey through time and space: from scattered centres of power to the emergence of the palace at Ano Engliano...

✅ **5. Minoan and Mycenaean gold signet rings: craft traditions, knowledge transmission and cultural labels**
- URL: https://www.repository.cam.ac.uk/items/7e68727d-9702-497c-8cc7-42d0ad2939de
- Score: 0.2802
- 预览: Gold signet rings are iconic artefacts of the Aegean Bronze Age. Behind their visual impact, they hold information about craft virtuosity; the movemen...

### V5_v7_style

**查询**: `"Ring of Nestor" Pylos Messenia artifact authenticity provenance scholarly archaeology Bronze Age -site:en.wikipedia.org`

**描述**: V7 的实际查询（相对更好）

✅ **1. some observations on the iconography of the 'ring of nestor'**
- URL: https://www.academia.edu/83658257/SOME_OBSERVATIONS_ON_THE_ICONOGRAPHY_OF_THE_RING_OF_NESTOR_
- Score: 0.6241
- 预览: The so-called Nestor Ring was found in 1924 and was accepted as authentic by Sir Arthur Evans whereas many other scholars condemned it as a forgery. I...

❌ **2. Treasures of Mycenaean Pylos | PDF | Mycenaean Greece | Troy**
- URL: https://www.scribd.com/document/936835546/Princes-of-Pylos
- Score: 0.5398
- 预览: The document details the exhibition 'The Kingdom of Pylos: Warrior-Princes of Mycenaean Greece,' co-organized by the J. Paul Getty Museum and the Hell...

✅ **3. [PDF] Nestor Bibliography of Aegean and Related Areas 2020 - UC Classics**
- URL: https://classics.uc.edu/nestor/images/stories/annual_issues/nestor_2020.pdf
- Score: 0.5328
- 预览: & Hudson Inc. ISBN 978-0-500-48055-7. §20201492 Vlachopoulos, Andreas G. 2020. “The Ring of Nestor and the Quest for Authenticity.” Pp. 223-252 in Cur...

❌ **4. Pylos of Nestor A Mycenaean Kingdom Revealed**
- URL: https://www.namuseum.gr/en/temporary_exhibition/pylos-of-nestor-a-mycenaean-kingdom-revealed
- Score: 0.4255
- 预览: The long-term and systematic research conducted by foreign Archaeological Schools, the Archaeological Society at Athens and the University of Athens, ...

❌ **5. Rare archaeological finds in Pylos**
- URL: https://www.archaeology.wiki/blog/2015/10/27/rare-archaeological-finds-pylos
- Score: 0.4148
- 预览: # Rare archaeological finds in Pylos  ## Discovered by University of Cincinnati researchers  An international team of archaeologists led by University...

---

## 关键发现

### 1. 排除 Wikipedia 后的搜索效果
即使排除了 Wikipedia，Tavily 仍能返回相关的学术来源（如 Academia.edu、JSTOR、HathiTrust）。
关键是查询要**简洁精准**，而非堆砌泛化关键词。

### 2. GraphResearcher 查询问题
V8 的查询 `"Ring of Nestor Mycenaean gold ring archaeological study museum collection scholarly publication provenance iconography dating"` 
过于冗长，导致搜索引擎返回的是展览页面而非学术资料。

### 3. 有效查询策略
- ✅ `"Ring of Nestor" Arthur Evans Ashmolean Museum` - 精准标识符
- ✅ `"Ring of Nestor" gold signet ring Arthur Evans 1925` - 具体年份
- ❌ 堆砌 10+ 泛化关键词

---

*报告自动生成*
