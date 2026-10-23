from app.privacy import mask_pii


def test_masks_card_iban_email_phone_and_name():
    text, counts = mask_pii(
        "I am Arben Krasniqi. Card 4111-1111-1111-1111, IBAN XK05 1212 0123 4567 8906, "
        "email arben@example.com, phone 044 123 456. Arben here again.",
        names=["Arben Krasniqi"],
    )
    assert text == ("I am [CUSTOMER]. Card [CARD_NUMBER], IBAN [IBAN], "
                    "email [EMAIL], phone [PHONE]. [CUSTOMER] here again.")
    assert counts == {"IBAN": 1, "CARD_NUMBER": 1, "EMAIL": 1, "PHONE": 1, "NAME": 2}


def test_keeps_amounts_dates_and_ids():
    text = "Charged 1,450.00 EUR on 2026-10-21 at 03:17, transaction T2001, 23.40 twice"
    assert mask_pii(text) == (text, {})