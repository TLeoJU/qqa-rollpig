# Third-Party Notices

This repository is an adapter for **RollPig Plus**. It does not vendor the
upstream Python package; the installer fetches it from PyPI. The upstream
package, fonts, emoji assets, pig images, and copy are **not** covered by this
repository's MIT license.

## RollPig Plus

- Project: <https://github.com/Felis2026/nonebot-plugin-rollpig-plus>
- PyPI: `nonebot-plugin-rollpig-plus==0.14.4`
- License: **MIT**
- Copyright: Copyright (c) 2025 Bear_lele; Copyright (c) 2025-2026 Felis
- Full text: [`LICENSES/RollPig-Plus-MIT.txt`](LICENSES/RollPig-Plus-MIT.txt)
- Relationship: installed as a runtime dependency and loaded unchanged by the
  headless sidecar. This repository contains only the QQA adapter, sidecar
  launcher, installer, and help-image generator.

RollPig Plus was originally based on
[Bearlele/nonebot-plugin-rollpig](https://github.com/Bearlele/nonebot-plugin-rollpig).
The upstream README asks users not to load the original and Plus versions in the
same NoneBot process; this adapter avoids that by running Plus in a separate
sidecar process.

## Fonts

The following fonts are bundled with the upstream package and/or used to render
the `plugin/assets/rollpig-help.png` image:

| Asset | Upstream source | License |
| --- | --- | --- |
| Source Han Sans SC Medium (`SourceHanSansSC-Medium.otf`) | [adobe-fonts/source-han-sans](https://github.com/adobe-fonts/source-han-sans) | SIL Open Font License 1.1 |
| ZCOOL KuaiLe Regular (`ZCOOLKuaiLe-Regular.ttf`) | [google/fonts — zcoolkuaile](https://github.com/google/fonts/tree/main/ofl/zcoolkuaile) | SIL Open Font License 1.1 |
| RollPig Daily Serif subsets (`RollPigDailySerif-*.subset.otf`) | [notofonts/noto-cjk](https://github.com/notofonts/noto-cjk) | SIL Open Font License 1.1 |

A copy of the OFL 1.1 text is provided at
[`LICENSES/OFL-1.1.txt`](LICENSES/OFL-1.1.txt).

The help image is a rendered output using these fonts; the font files
themselves are not redistributed in this repository. If you redistribute the
image, keep the attribution above.

## Emoji assets

- **Google Noto Emoji PNG assets**
  - Source: <https://github.com/googlefonts/noto-emoji>
  - Bundled by upstream as `resource/emoji/google-emoji.zip`
  - Usage: offline color emoji rendering through `pilmoji`
  - License: depending on the specific asset/revision, **SIL OFL 1.1** or
    **Apache License 2.0**
  - Copies: [`LICENSES/OFL-1.1.txt`](LICENSES/OFL-1.1.txt),
    [`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt)

## pilmoji

- Source: <https://github.com/jay3332/pilmoji>
- Usage: text/emoji drawing helper for Pillow cards
- License: see the upstream package metadata distributed with `pilmoji`

## Pig images, GIFs, and copy

RollPig's public resources are maintained separately:

- <https://github.com/Felis2026/rollpig-resources>
- <https://pighub.top/>

The images, GIF overlays, and shared roast copy are **not** MIT-licensed by this
repository. Their source, attribution, and redistribution terms are governed by
the resource repository and the original uploaders. Do not assume that the MIT
license of the adapter code applies to them.

## QQ Agent

- QQ Agent / QQA is the host application. This repository only adds a plugin
  and a sidecar; QQA itself is not redistributed here.

## This repository

The adapter code (plugin, sidecar launcher, scripts, docs, help-image generator)
is MIT-licensed; see [`LICENSE`](LICENSE).
