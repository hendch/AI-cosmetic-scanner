from .schemas import RetrieveRequest, RetrieveResponse, EvidenceItem

def mock_retrieve(req: RetrieveRequest) -> RetrieveResponse:
    if req.ingredient.strip().lower() == "unknownium":   # test case for "not covered"
        return RetrieveResponse(ingredient=req.ingredient, strategy=req.strategy,
                                covered=False, results=[])
    return RetrieveResponse(
        ingredient=req.ingredient, strategy=req.strategy, covered=True,
        results=[EvidenceItem(
            evidence_id="EV-MOCK-001",
            text="MOCK: Placeholder restriction text for " + req.ingredient,
            score=0.82,
            source="EU Cosmetics Regulation 1223/2009",
            section="Annex V",
            source_date="2024-01-01",
            url="https://eur-lex.europa.eu/",
            metadata={"ingredient": req.ingredient.lower(), "annex": "V",
                      "status": "restricted"},
        )],
    )