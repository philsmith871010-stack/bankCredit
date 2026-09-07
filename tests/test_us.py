import fitz

from bankcredit.extract import us


def _pdf(tmp_path, lines):
    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for l in lines:
        page.insert_text((50, y), l, fontsize=10)
        y += 16
    path = tmp_path / "gs.pdf"
    doc.save(str(path))
    return str(path)


def test_requirement_blocks_are_not_read_as_actual_ratios(tmp_path):
    # Goldman's Table 1: minimums, then total requirements, then the actual ratios, same labels each time
    path = _pdf(tmp_path, [
        "Basel III Pillar 3 Disclosures as of June 30, 2026",
        "Table 1: Regulatory Capital Ratios",
        "Minimum capital ratios",
        "CET1 capital ratio 4.5%",
        "Tier 1 capital ratio 6.0%",
        "Total capital ratio 8.0%",
        "Total capital requirements including buffers",
        "CET1 capital ratio 10.4%",
        "Tier 1 capital ratio 11.9%",
        "Total capital ratio 13.9%",
        "Regulatory capital ratios as of June 30, 2026",
        "CET1 capital ratio 13.6%",
        "Tier 1 capital ratio 15.2%",
        "Total capital ratio 16.8%",
        "Supplementary leverage ratio 5.5%",
    ])
    res = us.extract_capital(path)
    assert res.values["cet1_ratio"] == 13.6
    assert res.values["tier1_ratio"] == 15.2 and res.values["total_capital_ratio"] == 16.8
    assert res.values["leverage_ratio"] == 5.5
