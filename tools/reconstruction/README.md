# 关键重建工具

这些文件来自本批素材制作使用的转换流程，保留了路径、裁剪、填充和字形处理逻辑。仓库路径已改为相对定位，不包含本地依赖副本。

| 文件 | 作用 |
| --- | --- |
| `extract_svg.py` | 按PDF页码与裁剪框提取SVG，解析路径、图层、透明度和图像 |
| `build_figures.mjs` | 使用本地ArtifactTool运行时把提取结果建成原生PPT形状 |
| `patch_figures.py` | 恢复DrawingML曲线、填充规则、虚线和线端等属性 |
| `solid_path.py`、`winding.py` | 处理复合路径、轮廓方向和填充 |
| `line_repairs.json` | 以源文件指纹约束的特定线条修正记录 |

## 运行前提

- Python依赖见`../requirements-reconstruction.txt`，版本对应本批实际使用环境。
- JavaScript工具需要当前环境能解析`@oai/artifact-tool`。本仓库不随附该运行时，也不假定它能从公共包仓库直接安装。
- 导出预览和SVG需要LibreOffice的`soffice`及Poppler的`pdftocairo`。
- 原论文PDF由使用者从对应来源取得，并先核对版本指纹。

## 自动路径的调用顺序

在仓库根目录准备清单，格式见[示例](../../examples/manifest.example.json)。示例中的题名、图号和裁剪框需要换成实际核验的值。

```bash
python3 -m pip install -r tools/requirements-reconstruction.txt
python3 tools/reconstruction/extract_svg.py work/manifest.json work/figures
node tools/reconstruction/build_figures.mjs work/figures/SEC-101
python3 tools/reconstruction/patch_figures.py work/figures/SEC-101
soffice --headless --convert-to pdf --outdir work/figures/SEC-101/render work/figures/SEC-101/figure.pptx
pdftocairo -svg work/figures/SEC-101/render/figure.pdf work/figures/SEC-101/figure.svg
```

请对照原图检查输出。位图框架、特殊数学布局或复杂裁剪可能需要改用原生重绘、作者绘图源文件，或针对具体图修正。运行成功并不表示图已复刻准确。

这些工具展示通用的矢量转换路径；各张人工重绘图的取舍不能仅由这个命令序列自动重建。制作中的分支判断与实例见[制作方法](../../docs/METHOD.md)。
