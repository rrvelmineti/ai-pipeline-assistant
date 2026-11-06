# Claims file review for a synthetic client (sample file)

We checked all 2,000 rows of your claims file against the onboarding rules.

**The file is not ready yet.** We found 42 problems that must be fixed across 42 rows. Please correct them in your source system and resend the whole file.

## Must fix before go-live

### Rendering NPI: exactly 10 digits (6 rows)

Check the identifier's length and remove spaces, dashes or letters.

| Line | Value sent | Problem |
| --- | --- | --- |
| 388 | 196467754 | Expected exactly 10 digits; found 9 characters. |
| 664 | 196178775 | Expected exactly 10 digits; found 9 characters. |
| 1249 | 157883562 | Expected exactly 10 digits; found 9 characters. |
| 1279 | 185367247 | Expected exactly 10 digits; found 9 characters. |
| 1339 | 173289841 | Expected exactly 10 digits; found 9 characters. |

The attached findings file lists all 6 rows.

### Clm_Nbr: unique (5 rows)

Each value must appear once. Remove duplicate rows or correct the repeated identifiers.

| Line | Value sent | Problem |
| --- | --- | --- |
| 683 | CLM1000038 | Duplicate of line 40. |
| 712 | CLM1000165 | Duplicate of line 167. |
| 900 | CLM1000149 | Duplicate of line 151. |
| 914 | CLM1000090 | Duplicate of line 92. |
| 1146 | CLM1000060 | Duplicate of line 62. |

### Subscriber Ref: required (4 rows)

Fill in the missing values from your source system. We cannot guess them.

| Line | Value sent | Problem |
| --- | --- | --- |
| 331 | (blank) | Missing value. |
| 1453 | (blank) | Missing value. |
| 1604 | (blank) | Missing value. |
| 1770 | (blank) | Missing value. |

### Plan Paid Amt: not greater than Total Charges (4 rows)

This amount cannot be larger than the related amount on the same row.

| Line | Value sent | Problem |
| --- | --- | --- |
| 566 | 427.20 | Greater than Total Charges (327.20). |
| 575 | 1857.41 | Greater than Total Charges (1757.41). |
| 939 | 1283.29 | Greater than Total Charges (1183.29). |
| 1411 | 1001.14 | Greater than Total Charges (901.14). |

### Primary Dx: ICD-10 format (4 rows)

Send ICD-10-CM diagnosis codes, such as E11.9.

| Line | Value sent | Problem |
| --- | --- | --- |
| 1091 | DIABETES | Does not look like an ICD-10-CM code (for example E11.9). |
| 1440 | DIABETES | Does not look like an ICD-10-CM code (for example E11.9). |
| 1470 | E11.95X7Q | Does not look like an ICD-10-CM code (for example E11.9). |
| 1958 | 119.0 | Does not look like an ICD-10-CM code (for example E11.9). |

### DOS_From: date YYYY-MM-DD (3 rows)

Send every date in the stated format, for example 2026-03-31.

| Line | Value sent | Problem |
| --- | --- | --- |
| 576 | 05/14/2025 | Not a valid date in YYYY-MM-DD format. |
| 1355 | 09/05/2026 | Not a valid date in YYYY-MM-DD format. |
| 1846 | 06/30/2026 | Not a valid date in YYYY-MM-DD format. |

### Svc Code: exactly 5 characters (3 rows)

Check the code's length; codes may have lost or gained characters on export.

| Line | Value sent | Problem |
| --- | --- | --- |
| 894 | 9300 | Expected exactly 5 characters; found 4. |
| 1483 | 9300 | Expected exactly 5 characters; found 4. |
| 1562 | 9921 | Expected exactly 5 characters; found 4. |

### Claim Sts: one of paid / denied / pending / adjusted (3 rows)

Use only the allowed values listed for this field.

| Line | Value sent | Problem |
| --- | --- | --- |
| 1018 | approved | Not one of the allowed values: paid / denied / pending / adjusted. |
| 1156 | approved | Not one of the allowed values: paid / denied / pending / adjusted. |
| 1766 | approved | Not one of the allowed values: paid / denied / pending / adjusted. |

### DOS_From: not in the future (3 rows)

Dates cannot be after the extract date. Check for typing or conversion errors.

| Line | Value sent | Problem |
| --- | --- | --- |
| 1118 | 2028-03-15 | Date is after today (2026-11-05). |
| 1378 | 2028-01-15 | Date is after today (2026-11-05). |
| 1717 | 2028-04-15 | Date is after today (2026-11-05). |

### Total Charges: number (3 rows)

Send plain numbers such as 125.50, without currency symbols, commas or words.

| Line | Value sent | Problem |
| --- | --- | --- |
| 1714 | $772.42 | Not a plain number. Remove currency symbols, commas and words. |
| 1780 | $2131.63 | Not a plain number. Remove currency symbols, commas and words. |
| 1819 | $1341.83 | Not a plain number. Remove currency symbols, commas and words. |

### DOS_From: not before Patient Birth Dt (2 rows)

This date cannot be earlier than the related date on the same row.

| Line | Value sent | Problem |
| --- | --- | --- |
| 973 | 2025-06-15 | Earlier than Patient Birth Dt (2026-10-01). |
| 1903 | 2025-06-15 | Earlier than Patient Birth Dt (2026-10-01). |

### Plan Paid Amt: not negative (2 rows)

Amounts must be zero or more. Check for reversals exported as negatives.

| Line | Value sent | Problem |
| --- | --- | --- |
| 1098 | -15.00 | Negative value. |
| 1263 | -15.00 | Negative value. |


## Please review

These do not block go-live, but please confirm or correct them.

### POS: exactly 2 digits (5 rows)

Check the identifier's length and remove spaces, dashes or letters.

| Line | Value sent | Problem |
| --- | --- | --- |
| 405 | 110 | Expected exactly 2 digits; found 3 characters. |
| 478 | 110 | Expected exactly 2 digits; found 3 characters. |
| 652 | 110 | Expected exactly 2 digits; found 3 characters. |
| 977 | 110 | Expected exactly 2 digits; found 3 characters. |
| 1578 | 110 | Expected exactly 2 digits; found 3 characters. |

### Allowed Amt: not greater than Total Charges (5 rows)

This amount cannot be larger than the related amount on the same row.

| Line | Value sent | Problem |
| --- | --- | --- |
| 807 | 1619.07 | Greater than Total Charges (1519.07). |
| 960 | 2341.50 | Greater than Total Charges (2241.50). |
| 1105 | 318.52 | Greater than Total Charges (218.52). |
| 1833 | 544.33 | Greater than Total Charges (444.33). |
| 1852 | 2122.38 | Greater than Total Charges (2022.38). |


Line numbers are physical lines in the file you sent, counting the header as line 1.
