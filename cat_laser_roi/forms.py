# your_app/forms.py
from django import forms

class OptimizationForm(forms.Form):
    stock_length = forms.IntegerField(
        label="Chiều dài cây sắt (mm)", 
        initial=6000
    )
    trim_start = forms.IntegerField(
        label="Tề đầu sắt (mm)",
        initial=10,
        min_value=0,
        max_value=100,
        help_text="Phần sắt bị cắt bỏ ở đầu cây (mặc định 10mm)"
    )
    max_waste_percentage = forms.DecimalField(
        label="Hao hụt sắt tối đa (%)", 
        initial=1.0,
        min_value=0.01,
        max_value=10.0,
        decimal_places=2
    )
    max_surplus = forms.IntegerField(
        label="Cho phép chênh lệch (SL đoạn/ mỗi kích thước đoạn)", 
        initial=10,
        help_text="Cho phép thừa hoặc thiếu trong phạm vi này"
    )
    max_total_surplus = forms.IntegerField(
        label="Tổng tồn kho tối đa (tất cả loại)",
        initial=1000,
        required=False,
        help_text="Giới hạn tổng số đoạn tồn kho của tất cả các loại cộng lại (chỉ áp dụng khi tìm chiều dài tối ưu)"
    )
    use_priority_constraint = forms.BooleanField(
        label="Ưu tiên pattern có đoạn cuối khoét lỗ ít nhất", 
        required=False, 
        initial=True
    )
    pattern_limit = forms.IntegerField(
        label="Số lượng patterns tối đa",
        initial=100000,
        min_value=1000,
        max_value=100000,
        required=False,
    )
    use_combined_mode = forms.BooleanField(
        label="Chế độ cắt kết hợp Laser + Tự động", 
        required=False, 
        initial=False
    )
    optimize_stock_length = forms.BooleanField(
        label="Tự động tìm chiều dài cây sắt tối ưu (5000-6000mm)",
        required=False,
        initial=False
    )
    optimize_min_length = forms.IntegerField(
        label="Chiều dài bắt đầu (mm)",
        initial=5000,
        min_value=1000,
        max_value=10000,
        required=False,
        help_text="Chiều dài cây sắt tối thiểu để thử nghiệm"
    )
    optimize_max_length = forms.IntegerField(
        label="Chiều dài kết thúc (mm)",
        initial=6000,
        min_value=1000,
        max_value=10000,
        required=False,
        help_text="Chiều dài cây sắt tối đa để thử nghiệm"
    )
    optimize_search_step = forms.IntegerField(
        label="Bước nhảy tìm kiếm (mm)",
        initial=10,
        min_value=1,
        max_value=100,
        required=False,
        help_text="Bước nhảy giữa các chiều dài khi tìm kiếm (10mm = 101 tests, 50mm = 21 tests)"
    )
    optimize_stop_on_first = forms.BooleanField(
        label="Dừng ngay khi tìm thấy nghiệm khả thi đầu tiên",
        required=False,
        initial=False,
        help_text="Khi bật, sẽ dừng tìm kiếm ngay khi tìm thấy nghiệm khả thi đầu tiên (nhanh hơn nhưng có thể không tối ưu nhất)"
    )
    time_limit_minutes = forms.IntegerField(
        label="Thời gian chạy tối đa (3x phút)", 
        initial=2
    )