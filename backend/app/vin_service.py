from app.vin_schemas import VinCheckStatusOut


def vin_check_status() -> VinCheckStatusOut:
    """Report whether a verified VIN provider is enabled.

    No provider is selected for the pilot. This status function never accepts
    a VIN, stores a request, or fabricates a report.
    """
    return VinCheckStatusOut(
        available=False,
        provider=None,
        supported_categories=[],
        message="Поставщик проверки VIN пока не подключён.",
    )
