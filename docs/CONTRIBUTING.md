# 后续增补与维护

[返回 README](../README.md)

## 增加一张图

1. 先查[已涉及论文清单](../catalog/papers.md)及其[JSON](../catalog/papers.json)，同时核对正式题名、别名、论文标识和PDF指纹。
2. 核对官方奖项与论文版本，再对照该论文已用的图号和构图。同一图的重新裁剪或轻微变化不作为新素材。
3. 写清独立借鉴点，选择对应类型。既有论文保留原`PAPER-xxxx`编号；新论文在论文清单中登记新的稳定编号。
4. 在`figures/<方向>/<类型>/<ID>/`提供PPTX、SVG、原图、预览和元数据，保持已有素材编号不变。
5. 更新`catalog/figures.json`、`catalog/papers.json`和来源记录；修改图形后更新校验值，并重新对照实际渲染。不要只改校验值来隐藏未完成的检查。
6. 合并主库并更新页码，生成索引，运行检查，最后检查主PPT的实际显示效果。

```bash
python3 tools/update_catalog.py
python3 tools/check_library.py
```

检查工具会拒绝重复素材ID、相同论文的同一图，以及不同论文编号占用相同身份键。题名相似但不能确认是同一篇时，需要人工核对，不按相似度自动合并。

## 保留修改证据

每次修改记录来源、原因和验证范围。只改备注时，仍需区分PPT文件哈希与视觉载荷哈希；图形本身变化后，应重新渲染并检查，而不是沿用旧的视觉通过记录。

若完成了此前待做的PowerPoint原生程序检查，请一并更新`validation/status.json`、本批主库的验证记录和README状态。

## 仓库体积

当前所有单文件都低于GitHub普通Git的100MiB上限，仓库直接保存PPTX/SVG/PNG。GitHub会对超过50MiB的文件给出提示；后续增长或频繁保存大版本时，可考虑Git LFS或Release资产，并同步调整下载与校验说明。[GitHub文件体积说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

不要把依赖缓存、原始运行日志、凭据、机器绝对路径或本地字体库加入仓库。原论文用URL和版本指纹定位；第三方内容遵循各自来源许可。
