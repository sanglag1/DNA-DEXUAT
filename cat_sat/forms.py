# d:\IEA\cat_sat_iea\cat_sat\forms.py
from django import forms

class OptimizationForm(forms.Form):
    LENGTH_CHOICES = [(3650, '3650'), (5740, '5740'), (5850, '5850'), (5900, '5900'), (6000, '6000')]
    BLADE_WIDTH_CHOICES = [(1, '1'), (2.5, '2.5'), (3, '3')]

    length = forms.ChoiceField(
        choices=LENGTH_CHOICES,
        label="Chiều dài thanh sắt (mm)",
        initial=5850,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    te_dau_sat = forms.IntegerField(
        label="Tề đầu sắt (mm)",
        initial=0,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    # === XÓA 2 TRƯỜNG NÀY ===
    # segment_sizes = forms.CharField(...)
    # demands = forms.CharField(...)
    # ========================

    blade_width = forms.ChoiceField(
        choices=BLADE_WIDTH_CHOICES,
        label="Độ dày lưỡi cắt (mm)",
        initial=2.5,
        widget=forms.Select(attrs={'class': 'form-select'}) # <-- Sửa 'form-control' thành 'form-select'
    )

    factors = forms.CharField(
        label="Cây/bó",
        initial="14 16 18 20",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    no_bundle_constraint = forms.BooleanField(
        label="Không ràng buộc bó sắt (tính theo cây)",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    time_limit_minutes = forms.IntegerField(
        label="Thời gian chạy tối đa (phút)",
        initial=2,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    max_manual_cuts = forms.IntegerField(
        label="Số lần cắt thủ công tối đa (lần)",
        initial=5,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    max_stock_over = forms.IntegerField(
        label="Cho phép chênh lệch (SL đoạn/ mỗi kích thước đoạn)",
        initial=20,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        help_text="Cho phép thừa hoặc thiếu trong phạm vi này"
    )

    hao_hut_percent = forms.FloatField(
        label="Hao hụt tối đa (%)",
        initial=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0.1', 'max': '10'})
    )