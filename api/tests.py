"""
Test cho api_de_xuat_propose - đặc biệt 2 tham số RIÊNG theo từng loại sắt:
max_waste_percentage_by_material (ngưỡng hao hụt) và stock_lengths_by_material (chiều dài cây),
xem views.py + docstring endpoint.

Dùng SimpleTestCase (KHÔNG dựng test DB - view này không chạm DB nào) + mock optimize_one_material
(giữ CP-SAT ngoài phạm vi test, chỉ kiểm tra đúng tham số nào được truyền vào solver theo từng
loại sắt). list_material_groups KHÔNG mock - nó thuần và nhanh, và chính là phần chứng minh
việc gộp BOM -> group["material"] đúng như max_waste_percentage_by_material kỳ vọng khớp khoá.
"""
import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings

API_KEY = "test-key"
URL = "/api/v1/de_xuat/propose/"


def _feasible_result(waste_pct=0.5):
    """Kết quả tối thiểu optimize_one_material trả về khi feasible=True - đủ field để
    api_de_xuat_propose không lỗi lúc build response."""
    return {
        "feasible": True,
        "cut_lengths": [660.0],
        "demands": [100],
        "produced": [100],
        "best_length": 6000,
        "source": "fixed",
        "total_bars": 12,
        "waste_pct": waste_pct,
        "plan": [],
        "total_waste_mm": 100,
        "total_purchased_mm": 72000,
        "total_surplus_pieces": 0,
        "mau_nguyen_mm": 0,
        "over_waste": False,
        "max_waste_pct": waste_pct,
        "timeout_count": 0,
        "timeout_lengths": [],
        "auto_scan": False,
        "scan_stopped_early": False,
        "patterns_truncated": False,
        "fixed_evals": [],
        "scan_optimal": None,
    }


def _bom_row(material, cut_length=660.0):
    return {
        "part": "chân bàn",
        "qty_per_set": 4,
        "material": material,
        "spec": "",
        "cut_length": cut_length,
        "qty_per_part": 1,
    }


@override_settings(ERP_API_KEY=API_KEY)
class DeXuatProposeWastePctByMaterialTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {API_KEY}"}

    def _post(self, body):
        return self.client.post(
            URL, data=json.dumps(body), content_type="application/json", **self.headers
        )

    def _base_body(self, bom, **overrides):
        body = {
            "num_sets": 1,
            "bom": bom,
            "stock_lengths": "5850 6000",
            "trim_start": 10,
            "blade_width": 1.0,
            "max_waste_percentage": 1.0,
            "max_surplus": 10,
            "auto_scan": False,
        }
        body.update(overrides)
        return body

    @patch("api.views.optimize_one_material")
    def test_khong_gui_dict_thi_moi_loai_dung_nguong_mac_dinh(self, mock_optimize):
        """Không gửi max_waste_percentage_by_material -> hành vi y hệt trước khi có tính năng
        này (test backward-compat - quan trọng nhất trong cả bộ)."""
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200"), _bom_row("300")]

        res = self._post(self._base_body(bom))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_optimize.call_count, 2)
        for call in mock_optimize.call_args_list:
            self.assertEqual(call.kwargs["max_waste_pct"], 1.0)
        data = res.json()
        self.assertEqual(
            data["input_echo"]["resolved_max_waste_pct_by_group"],
            {"200": 1.0, "300": 1.0},
        )
        self.assertEqual(data["input_echo"]["max_waste_percentage_by_material"], {})

    @patch("api.views.optimize_one_material")
    def test_key_khop_1_loai_thi_chi_loai_do_dung_nguong_rieng(self, mock_optimize):
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200"), _bom_row("300")]

        res = self._post(
            self._base_body(bom, max_waste_percentage_by_material={"200": 2.5})
        )

        self.assertEqual(res.status_code, 200)
        # material_groups giữ đúng thứ tự xuất hiện trong bom_rows (200 rồi 300) - explode_bom
        # không sắp xếp lại - nên đối chiếu theo thứ tự gọi mock là đủ, không cần tra ngược.
        thresholds = [call.kwargs["max_waste_pct"] for call in mock_optimize.call_args_list]
        self.assertEqual(thresholds, [2.5, 1.0])
        data = res.json()
        self.assertEqual(
            data["input_echo"]["resolved_max_waste_pct_by_group"],
            {"200": 2.5, "300": 1.0},
        )

    @patch("api.views.optimize_one_material")
    def test_key_khong_khop_loai_nao_thi_tat_ca_dung_mac_dinh(self, mock_optimize):
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200")]

        res = self._post(
            self._base_body(bom, max_waste_percentage_by_material={"999": 5.0})
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_optimize.call_args_list[0].kwargs["max_waste_pct"], 1.0)
        data = res.json()
        # Dict thô vẫn còn "999" (client gửi gì thì echo đúng cái đó)...
        self.assertEqual(data["input_echo"]["max_waste_percentage_by_material"], {"999": 5.0})
        # ...nhưng resolved rơi về mặc định cho loại thật (200) - đây là dấu hiệu key sai.
        self.assertEqual(
            data["input_echo"]["resolved_max_waste_pct_by_group"], {"200": 1.0}
        )

    @patch("api.views.optimize_one_material")
    def test_value_rac_bi_bo_qua_dung_mac_dinh(self, mock_optimize):
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200")]

        res = self._post(
            self._base_body(
                bom,
                max_waste_percentage_by_material={
                    "200a": "abc",  # không parse được thành số
                    "200b": -5,  # ngoài khoảng (0, 100]
                    "200c": 0,  # = 0, bẫy vô nghiệm, bị loại
                    "200d": None,
                },
            )
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_optimize.call_args_list[0].kwargs["max_waste_pct"], 1.0)
        data = res.json()
        self.assertEqual(data["input_echo"]["max_waste_percentage_by_material"], {})

    @patch("api.views.optimize_one_material")
    def test_khong_phai_dict_thi_bo_qua_toan_bo(self, mock_optimize):
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200")]

        res = self._post(
            self._base_body(bom, max_waste_percentage_by_material=["not", "a", "dict"])
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_optimize.call_args_list[0].kwargs["max_waste_pct"], 1.0)

    @patch("api.views.optimize_one_material")
    def test_infeasible_item_van_co_max_waste_pct_threshold_dung(self, mock_optimize):
        """Loại vô nghiệm hoàn toàn vẫn phải cho biết ngưỡng nào đã áp - không thì UI không biết
        nới ngưỡng nào."""
        mock_optimize.return_value = {"feasible": False, "reason": "test"}
        bom = [_bom_row("200")]

        res = self._post(
            self._base_body(bom, max_waste_percentage_by_material={"200": 0.3})
        )

        self.assertEqual(res.status_code, 200)
        item = res.json()["purchase_plan"][0]
        self.assertEqual(item["feasible"], False)
        self.assertEqual(item["max_waste_pct_threshold"], 0.3)

    def test_thieu_api_key_bi_tu_choi(self):
        """require_api_key vẫn phải áp dụng bình thường - không bị tính năng mới bỏ sót."""
        res = self.client.post(
            URL, data=json.dumps(self._base_body([_bom_row("200")])),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 401)


@override_settings(ERP_API_KEY=API_KEY)
class DeXuatProposeStockLengthsByMaterialTests(SimpleTestCase):
    """stock_lengths_by_material - chiều dài cây RIÊNG theo từng loại sắt (2026-09-16).

    Cùng khuôn với DeXuatProposeWastePctByMaterialTests ở trên: mock optimize_one_material rồi
    kiểm tra ĐÚNG danh sách chiều dài nào được truyền vào cho từng loại. Điểm cần khoá lại là
    optimize_one_material vốn đã nhận stock_lengths theo từng lời gọi, nên bug dễ xảy ra nhất
    không phải ở thuật toán mà ở chỗ NỐI DÂY: truyền nhầm stock_lengths chung cho mọi loại.
    """

    def setUp(self):
        self.client = Client()
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {API_KEY}"}

    def _post(self, body):
        return self.client.post(
            URL, data=json.dumps(body), content_type="application/json", **self.headers
        )

    def _base_body(self, bom, **overrides):
        body = {
            "num_sets": 1,
            "bom": bom,
            "stock_lengths": "5850 6000",
            "trim_start": 10,
            "blade_width": 1.0,
            "max_waste_percentage": 1.0,
            "max_surplus": 10,
            "auto_scan": False,
        }
        body.update(overrides)
        return body

    @patch("api.views.optimize_one_material")
    def test_khong_gui_dict_thi_moi_loai_dung_stock_lengths_chung(self, mock_optimize):
        """Không gửi stock_lengths_by_material -> hành vi y hệt trước khi có tính năng này
        (backward-compat - test quan trọng nhất trong bộ)."""
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200"), _bom_row("300")]

        res = self._post(self._base_body(bom))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(mock_optimize.call_count, 2)
        for call in mock_optimize.call_args_list:
            self.assertEqual(call.kwargs["stock_lengths"], [5850.0, 6000.0])
        data = res.json()
        self.assertEqual(data["input_echo"]["stock_lengths_by_material"], {})
        self.assertEqual(
            data["input_echo"]["resolved_stock_lengths_by_group"],
            {"200": [5850.0, 6000.0], "300": [5850.0, 6000.0]},
        )

    @patch("api.views.optimize_one_material")
    def test_key_khop_1_loai_thi_chi_loai_do_dung_chieu_dai_rieng(self, mock_optimize):
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200"), _bom_row("300")]

        res = self._post(
            self._base_body(bom, stock_lengths_by_material={"200": [5850]})
        )

        self.assertEqual(res.status_code, 200)
        # material_groups giữ đúng thứ tự xuất hiện trong bom_rows (200 rồi 300).
        lengths = [call.kwargs["stock_lengths"] for call in mock_optimize.call_args_list]
        self.assertEqual(lengths, [[5850.0], [5850.0, 6000.0]])
        data = res.json()
        self.assertEqual(
            data["input_echo"]["resolved_stock_lengths_by_group"],
            {"200": [5850.0], "300": [5850.0, 6000.0]},
        )

    @patch("api.views.optimize_one_material")
    def test_key_khong_khop_loai_nao_thi_tat_ca_dung_chung(self, mock_optimize):
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200")]

        res = self._post(
            self._base_body(bom, stock_lengths_by_material={"999": [5850]})
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            mock_optimize.call_args_list[0].kwargs["stock_lengths"], [5850.0, 6000.0]
        )
        data = res.json()
        # Dict thô vẫn echo đúng cái client gửi...
        self.assertEqual(
            data["input_echo"]["stock_lengths_by_material"], {"999": [5850.0]}
        )
        # ...nhưng resolved rơi về chung cho loại thật (200) - dấu hiệu key sai.
        self.assertEqual(
            data["input_echo"]["resolved_stock_lengths_by_group"],
            {"200": [5850.0, 6000.0]},
        )

    @patch("api.views.optimize_one_material")
    def test_nhan_ca_3_dang_so_don_list_va_chuoi(self, mock_optimize):
        """Nhận số đơn / list / chuỗi - cùng luật với stock_lengths toàn cục."""
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200"), _bom_row("300"), _bom_row("400")]

        res = self._post(
            self._base_body(
                bom,
                stock_lengths_by_material={"200": 5850, "300": "6000, 5850", "400": [6000]},
            )
        )

        self.assertEqual(res.status_code, 200)
        lengths = [call.kwargs["stock_lengths"] for call in mock_optimize.call_args_list]
        self.assertEqual(lengths, [[5850.0], [5850.0, 6000.0], [6000.0]])

    @patch("api.views.optimize_one_material")
    def test_value_rac_va_so_khong_duong_bi_bo_qua(self, mock_optimize):
        """Giá trị rác / <= 0 -> bỏ qua entry đó, loại sắt rơi về stock_lengths chung (KHÔNG
        để danh sách rỗng lọt xuống solver - rỗng thì max(stock_lengths) nổ ValueError)."""
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200"), _bom_row("300")]

        res = self._post(
            self._base_body(bom, stock_lengths_by_material={"200": "abc", "300": [0, -5]})
        )

        self.assertEqual(res.status_code, 200)
        for call in mock_optimize.call_args_list:
            self.assertEqual(call.kwargs["stock_lengths"], [5850.0, 6000.0])
        self.assertEqual(res.json()["input_echo"]["stock_lengths_by_material"], {})

    @patch("api.views.optimize_one_material")
    def test_khong_phai_dict_thi_bo_qua_toan_bo(self, mock_optimize):
        mock_optimize.return_value = _feasible_result()
        bom = [_bom_row("200")]

        res = self._post(
            self._base_body(bom, stock_lengths_by_material=["5850", "6000"])
        )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            mock_optimize.call_args_list[0].kwargs["stock_lengths"], [5850.0, 6000.0]
        )
        self.assertEqual(res.json()["input_echo"]["stock_lengths_by_material"], {})
