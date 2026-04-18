import logging

logger = logging.getLogger(__name__)


def generate_feedback(data, command=""):
    """
    Generates coach feedback based on normalized activity data.
    Supports two modes:
      - Coach Canova Mode: triggered by '教练' or '分析' in the command
      - JuanWang Mode: default, personality-driven feedback
    """
    avg = data.get("heart_rate_avg", 0)
    max_hr = data.get("heart_rate_max", 0)
    dist = data.get("distance_meters", 0) / 1000
    pace = data.get("pace_avg", 0)

    # Coach Canova Mode
    if "教练" in command or "分析" in command:
        if pace > 0 and pace < 5.0:
            return (
                f"Coach Canova 点评：特定配速 {pace}min/km 保持得不错！"
                f"在 {dist:.1f}km 距离下，你的代谢适应正在增强。"
                f"注意核心姿态，这是高质量训练。💪"
            )
        return (
            f"Coach Canova 点评：今天进行了{dist:.1f}km的训练。"
            f"平均心率 {avg}，处于有效代谢区间。"
            f"建议在下一次长距离跑中增加特定配速的段落，追求质量而非单纯里程。"
        )

    # JuanWang Mode (Default)
    if avg > 145:
        return (
            f"🏃‍♂️ 闵文卷王提醒：刚才这次{dist:.1f}km跑得很拼啊！"
            f"平均心率 {avg}，最大 {max_hr}，"
            f"这强度有点高了，注意身体恢复，别让家属担心！😸"
        )
    elif avg > 0:
        return (
            f"🏃‍♂️ 闵文卷王点评：{dist:.1f}km 跑得非常稳！"
            f"平均心率 {avg}，最大 {max_hr}，"
            f"这节奏控制很成熟。基础扎实，继续保持，家属杯预热中！👍👍👍"
        )
    return f"🏃‍♂️ 闵文卷王收到记录：{dist:.1f}km 完成！今天的状态很不错，继续加油！"
