"""Fake CSV profiler output (what csvprofile writes), fed to the mock console command."""
import random
cols = ["FrameTime", "GameThreadTime", "RenderThreadTime", "GPUTime", "RHI/DrawCalls", "RHI/PrimitivesDrawn",
        "GPU/Basepass", "GPU/ShadowDepths", "GPU/LumenScreenProbeGather", "GPU/Translucency", "GPU/PostProcessing",
        "GPU/VolumetricFog", "GPU/HZB", "GPU/Unaccounted", "EVENTS"]
base = [27.5, 9.0, 11.2, 27.4, 4200, 9e6, 3.1, 7.8, 4.6, 5.9, 2.4, 1.4, 0.2, 0.9]
rows = [",".join(cols)]
random.seed(1)
for _ in range(120):
    rows.append(",".join(["%.3f" % (v * random.uniform(0.95, 1.05)) for v in base] + [""]))
rows.append("[HasHeaderRowAtEnd],1,[platform],Windows,[config],Development")
rows.append(",".join(cols))
U.SystemLibrary.CSV_TEXT = "\n".join(rows) + "\n"
