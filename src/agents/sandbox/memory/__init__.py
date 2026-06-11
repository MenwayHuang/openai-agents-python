"""中文学习提示：sandbox 长期记忆子包。

这里的代码负责把一次次 agent 运行记录保存成 rollout，再经过 phase one 抽取和
phase two 汇总，形成后续 run 可以读取的 memory_summary。当前 PPT Agent 起步阶段
可以先了解流程，不急着全量复刻。
"""
