# cat_laser/forms.py
from django import forms
import numpy as np # Import numpy for isnan check if needed

class OptimizationLaserForm(forms.Form):
    LENGTH_CHOICES = [(5740, '5740 mm'), (5850, '5850 mm'), (6000, '6000 mm')]
    BLADE_WIDTH_CHOICES = [(3.0, '3.0 mm'), (2.5, '2.5 mm')]

    laser_length = forms.ChoiceField(
        choices=LENGTH_CHOICES,
        label="Chiều dài cây sắt (mm)",
        initial=5850,
        widget=forms.Select(attrs={'class': 'form-control'}),
        # help_text="Chọn chiều dài chuẩn của vật liệu gốc."
    )

    laser_segment_sizes = forms.CharField(
        label="Kích thước đoạn",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ví dụ: 2360.8, 1684, 565'}),
        # help_text="Nhập danh sách các kích thước đoạn cần cắt."
    )

    laser_demands = forms.CharField(
        label="Số lượng cần",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ví dụ: 300, 600, 1200'}),
        # help_text="Nhập số lượng tương ứng với từng kích thước đoạn ở trên."
    )

    laser_blade_width_mctd = forms.ChoiceField(
        label="Hao hụt lưỡi cắt cho MCTĐ",
        choices=BLADE_WIDTH_CHOICES,
        initial=3.0, # Hao hụt mặc định cho đoạn nguyên
        widget=forms.Select(attrs={'class': 'form-control'}),
        # help_text=f"Hao hụt này áp dụng cho các đoạn có kích thước là số nguyên (ví dụ: 565). Các đoạn lẻ (ví dụ: 2360.8) sẽ dùng hao hụt mặc định {DEFAULT_BLADE_WASTE}mm."
    )

    laser_max_stock_over = forms.IntegerField(
        label="Tồn kho tối đa (cho mỗi loại đoạn)",
        initial=3,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control'}),
        # help_text="Giới hạn số lượng dư thừa cho phép sau khi hoàn thành đơn hàng."
    )

    # --- Phương thức Clean cho từng trường ---
    def clean_segment_sizes(self):
        """Parse và validate segment_sizes."""
        data = self.cleaned_data['segment_sizes']
        try:
            sizes = [float(s.strip()) for s in data.replace(',', ' ').split() if s.strip()]
            if not sizes:
                 raise forms.ValidationError("Bạn phải nhập ít nhất một kích thước đoạn.")
            if any(s <= 0 or np.isnan(s) for s in sizes): # Check for <= 0 or NaN
                 raise forms.ValidationError("Kích thước đoạn phải là số dương hợp lệ.")
            return sizes
        except ValueError:
            raise forms.ValidationError("Định dạng kích thước đoạn không hợp lệ. Chỉ nhập số, dấu phẩy, khoảng trắng.")

    def clean_demands(self):
        """Parse và validate demands."""
        data = self.cleaned_data['demands']
        try:
            demands = [int(d.strip()) for d in data.replace(',', ' ').split() if d.strip()]
            if not demands:
                 raise forms.ValidationError("Bạn phải nhập ít nhất một số lượng.")
            if any(d <= 0 for d in demands):
                 raise forms.ValidationError("Số lượng cần phải là số nguyên dương.")
            return demands
        except ValueError:
            raise forms.ValidationError("Định dạng số lượng không hợp lệ. Chỉ nhập số nguyên, dấu phẩy, khoảng trắng.")

    # --- Phương thức Clean tổng ---
    def clean(self):
        """Kiểm tra chéo giữa các trường."""
        cleaned_data = super().clean()
        segment_sizes = cleaned_data.get("segment_sizes")
        demands = cleaned_data.get("demands")

        # Kiểm tra độ dài khớp nhau
        if segment_sizes and demands:
            if len(segment_sizes) != len(demands):
                # Dùng add_error thay vì raise ValidationError để gắn lỗi vào field cụ thể nếu muốn
                self.add_error('demands', "Số lượng kích thước đoạn phải bằng số lượng yêu cầu.")
                # Hoặc raise chung:
                # raise forms.ValidationError("Số lượng kích thước đoạn phải bằng số lượng yêu cầu.")

        # Ép kiểu các giá trị số khác về đúng kiểu float/int
        try:
            if 'length' in cleaned_data:
                cleaned_data['length'] = float(cleaned_data['length'])
            if 'blade_width_mctd' in cleaned_data:
                # Lưu giá trị hao hụt thực tế đã chọn
                cleaned_data['blade_width_mctd_value'] = float(cleaned_data['blade_width_mctd'])
            if 'max_stock_over' in cleaned_data:
                 # Đã là Int do IntegerField, nhưng kiểm tra lại phòng trường hợp tùy chỉnh widget
                 cleaned_data['max_stock_over'] = int(cleaned_data['max_stock_over'])

        except (ValueError, TypeError) as e:
             # Lỗi này không nên xảy ra nếu ChoiceField/IntegerField hoạt động đúng
             # Nhưng thêm để phòng ngừa
             raise forms.ValidationError(f"Lỗi xử lý giá trị số trong form: {e}")


        return cleaned_data