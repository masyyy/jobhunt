"""The applicant this dashboard serves.

Kept in one place so both the relevance matcher and the application assistant
reason about the same person. Edit here to change who the dashboard is for.
"""

APPLICANT_PROFILE = """\
Young, outgoing woman with ADHD. Degree in marketing and graphic design, but
not well suited to traditional office or desk jobs. Experience: marketing
intern, and a salesperson (myyjä) at Suomalainen Kirjakauppa; crafts, graphic
design, scrapbooking and organizing at Lowe's.

Languages: fluent Spanish and English, plus Finnish at roughly B1 (intermediate;
good for everyday customer service, but not yet fully fluent in writing).

What fits her:
- Any low-level / entry-level retail or customer-facing shop work (myyjä,
  kassa, shop/sales assistant, asiakaspalvelu in a store).
- Best of all: bookstores and craft/hobby stores. Also good: lifestyle/variety
  stores (Normal, Tiger/Flying Tiger, Søstrene Grene, Tokmanni, Clas Ohlson),
  grocery stores, and similar shops.
- Temporary / seasonal positions in libraries and museums.
- Printing-related work: print shops, copy/print services, photo printing,
  digital printing, print finishing, and similar hands-on roles.
- Roles that can use her marketing or graphic-design skills in a hands-on,
  creative, non-office way are a plus, but not required.

What does NOT fit:
- B2B sales, telemarketing, commission-only sales, booking/buukkari roles.
- Managerial or team-lead positions (myymäläpäällikkö, sales manager, etc.).
- Pure office / specialist / technical roles (developer, accountant, engineer,
  consultant, controller, lawyer).
- Roles that require a formal qualification, license, degree, or vocational
  certification she does not have. She has a marketing/graphic-design degree
  and retail experience — nothing else. So exclude jobs that legally or
  practically require credentials she lacks, e.g.: teacher (opettaja,
  lastentarhanopettaja, sijaisopettaja), barber/hairdresser
  (parturi-kampaaja, kampaaja), nurse/practical nurse (sairaanhoitaja,
  lähihoitaja), licensed trades (sähköasentaja/electrician, kokki/trained
  cook, hitsaaja/welder), beautician/cosmetologist (kosmetologi), security
  guard requiring a card (vartija), driver needing a special licence
  (yhdistelmäajoneuvonkuljettaja), and similar credentialed professions.
"""
