# Field lineage contract

This is the map from external inputs to canonical model attributes and then to
XML. The exhaustive external-name-to-attribute dictionaries are
`CONFIG_KEY_MAP`, `FILING_KEY_MAP`, and `HOLDINGS_KEY_MAP` in
`src/nport/config.py`. `src/nport/models.py` defines the three canonical records.
`src/nport/builder.py` owns the XML paths below.

Every produced holding field and every supplied fund field is also written to
`field_provenance.csv` in the canonical run bundle. That file is the per-run,
per-record realization of this static contract.

The input workbook uses these same external field names without a second
mapping layer: `<FUND>_Config.fieldName` uses the operator-supplied subset of
`CONFIG_KEY_MAP`, `<FUND>_FundData.fieldName` uses the operator-supplied subset
of `FILING_KEY_MAP`, and each `<FUND>_Positions` column uses
`HOLDINGS_KEY_MAP`. System-derived fields and `liveTestFlag` are deliberately
absent from the input surface. The importer projects one fund-period into
canonical CSVs and the standard `filing_inputs.xlsx`; all model and XML mappings
below are then unchanged.

## FundConfig

| External input | Model attribute | XML target or control use |
|---|---|---|
| `cik`, `ccc` | `cik`, `ccc` | `headerData/filerInfo/filer/issuerCredentials/{cik,ccc}` |
| `regName`, `regFileNumber`, `regCik`, `regLei` | `reg_name`, `reg_file_number`, `reg_cik`, `reg_lei` | `formData/genInfo/{regName,regFileNumber,regCik,regLei}` |
| `regStreet1`, `regStreet2`, `regCity` | `reg_street1`, `reg_street2`, `reg_city` | `formData/genInfo/{regStreet1,regStreet2,regCity}`; street 2 is omitted when blank |
| `regCountry`, `regState` | `reg_country`, `reg_state` | `formData/genInfo/regStateConditional/@{regCountry,regState}` |
| `regZipOrPostalCode`, `regPhone` | `reg_zip`, `reg_phone` | `formData/genInfo/{regZipOrPostalCode,regPhone}` |
| `seriesName`, `seriesLei` | `series_name`, `series_lei` | `formData/genInfo/{seriesName,seriesLei}` |
| `seriesId` | `series_id` | `headerData/filerInfo/seriesClassInfo/seriesId` and `formData/genInfo/seriesId` |
| `classId` | `class_id` | `headerData/filerInfo/seriesClassInfo/classId` and `fundInfo/returnInfo/monthlyTotReturns/monthlyTotReturn/@classId` |
| `signerOrg` | `signer_org` | `formData/signature/ncom:nameOfApplicant` |
| `signerName` | `signer_name` | `formData/signature/ncom:signature` with `/s/ ` prefix and `ncom:signerName` |
| `signerTitle` | `signer_title` | `formData/signature/ncom:title` |
| `fiscalYearEndMMDD` | `fiscal_year_end_mmdd` | derives `FilingData.rep_pd_end`, `submission_type`, and `headerData/isConfidential` |
| `derivativesRegimePolicy` | `derivatives_regime_policy` | derives `FilingData.derivatives_regime`; gates B.9/B.10 |
| `liquidityRequired`, `cashB2fRequired` | `liquidity_required`, `cash_b2f_required` | preflight applicability gates for C.7 and B.2.f |
| `policyEffectiveFrom`, `policyEffectiveTo` | `policy_effective_from`, `policy_effective_to` | policy-effective-date gate |
| `policyApprovedBy`, `policyApprovedAt`, `policySourceRef` | `policy_approved_by`, `policy_approved_at`, `policy_source_ref` | governance metadata; not serialized to XML |
| `requiredSources` | `required_sources` | derived source-manifest coverage metadata; not serialized to XML |

## FilingData

The external names in `FundFields.fieldName` map to the snake-case attributes
shown here.

| External input | Model attribute(s) | XML target |
|---|---|---|
| `submissionType` | `submission_type` | `headerData/submissionType`; also derives `headerData/isConfidential` |
| `liveTestFlag` | `live_test_flag` | `headerData/filerInfo/liveTestFlag` for TEST; omitted for LIVE |
| `repPdEnd`, `repPdDate`, `isFinalFiling` | `rep_pd_end`, `rep_pd_date`, `is_final_filing` | `formData/genInfo/{repPdEnd,repPdDate,isFinalFiling}` |
| `dateSigned` | `date_signed` | `formData/signature/ncom:dateSigned` |
| `totAssets`, `totLiabs`, `netAssets` | `tot_assets`, `tot_liabs`, `net_assets` | `formData/fundInfo/{totAssets,totLiabs,netAssets}` |
| `assetsAttrMiscSec`, `assetsInvested` | `assets_attr_misc_sec`, `assets_invested` | `fundInfo/{assetsAttrMiscSec,assetsInvested}` |
| `amtPayOneYrBanksBorr`, `amtPayOneYrCtrldComp`, `amtPayOneYrOthAffil`, `amtPayOneYrOther` | matching `amt_pay_one_yr_*` attributes | matching children of `fundInfo` |
| `amtPayAftOneYrBanksBorr`, `amtPayAftOneYrCtrldComp`, `amtPayAftOneYrOthAffil`, `amtPayAftOneYrOther` | matching `amt_pay_aft_one_yr_*` attributes | matching children of `fundInfo` |
| `delayDeliv`, `standByCommit`, `liquidPref` | `delay_deliv`, `stand_by_commit`, `liquid_pref` | matching children of `fundInfo` |
| `cashNotReportedInCOrD` | `cash_not_reported_in_c_or_d` | optional `fundInfo/cshNotRptdInCorD` |
| `isNonCashCollateral` | `is_non_cash_collateral` | `fundInfo/isNonCashCollateral` |
| `rtn1`, `rtn2`, `rtn3` | `rtn1`, `rtn2`, `rtn3` | `returnInfo/monthlyTotReturns/monthlyTotReturn/@{rtn1,rtn2,rtn3}` |
| `netRealizedGainMon1`, `netUnrealizedApprMon1` | `net_realized_gain_mon1`, `net_unrealized_appr_mon1` | `returnInfo/othMon1/@{netRealizedGain,netUnrealizedAppr}` |
| `netRealizedGainMon2`, `netUnrealizedApprMon2` | `net_realized_gain_mon2`, `net_unrealized_appr_mon2` | `returnInfo/othMon2/@{netRealizedGain,netUnrealizedAppr}` |
| `netRealizedGainMon3`, `netUnrealizedApprMon3` | `net_realized_gain_mon3`, `net_unrealized_appr_mon3` | `returnInfo/othMon3/@{netRealizedGain,netUnrealizedAppr}` |
| `mon1Sales`, `mon1Redemption`, `mon1Reinvestment` | matching `mon1_*` attributes | `fundInfo/mon1Flow/@{sales,redemption,reinvestment}` |
| `mon2Sales`, `mon2Redemption`, `mon2Reinvestment` | matching `mon2_*` attributes | `fundInfo/mon2Flow/@{sales,redemption,reinvestment}` |
| `mon3Sales`, `mon3Redemption`, `mon3Reinvestment` | matching `mon3_*` attributes | `fundInfo/mon3Flow/@{sales,redemption,reinvestment}` |
| `curMetricsJson` | `cur_metrics_json` | expands to `fundInfo/curMetrics/curMetric/{curCd,intrstRtRiskdv01,intrstRtRiskdv100}` |
| `creditSprdRiskIgJson` | `credit_sprd_risk_ig_json` | expands to `fundInfo/creditSprdRiskInvstGrade` period attributes |
| `creditSprdRiskNonigJson` | `credit_sprd_risk_nonig_json` | expands to `fundInfo/creditSprdRiskNonInvstGrade` period attributes |
| `monthlyReturnCategoriesJson` | `monthly_return_categories_json` | expands to `returnInfo/monthlyReturnCats/<contract>/<month and instrument>` |
| `derivativesRegime` | `derivatives_regime` | control value only; determines whether B.9/B.10 is required/emitted |
| `derivExposurePct`, `derivCurrencyExposurePct`, `derivInterestRateExposurePct`, `derivDaysInExcess` | matching `deriv_*` attributes | `fundInfo/derivExposureInfo/{derivExposurePct,derivCurrencyExposurePct,derivIntRateExposurePct,noOfBusinessDaysInExcess}` |
| `medianDailyVarPct` | `median_daily_var_pct` | `fundInfo/varInfo/medianDailyVarPct` |
| `nameDesignatedIndex`, `indexIdentifier`, `medianVarRatioPct` | `name_designated_index`, `index_identifier`, `median_var_ratio_pct` | relative-VaR `varInfo/fundsDesignatedInfo/{nameDesignatedIndex,indexIdentifier,medianVarRatioPct}` |
| `backtestingExceptions` | `backtesting_exceptions` | `fundInfo/varInfo/backtestingResults` |

## Holding

Every input position becomes one `formData/invstOrSecs/invstOrSec`. The row key
is trace metadata and is not serialized.

| CSV column(s) | Model attribute(s) | XML target or rule |
|---|---|---|
| `name`, `lei`, `title`, `cusip` | same names | `invstOrSec/{name,lei,title,cusip}` |
| `isin`, `ticker` | same names | `identifiers/{isin,ticker}/@value`; omitted when blank |
| `otherDesc`, `otherValue` | `other_desc`, `other_value` | `identifiers/other/@{otherDesc,value}` |
| no usable ISIN/ticker/other + real CUSIP | `cusip` | deterministic `identifiers/other/@otherDesc="CUSIP"/@value=<cusip>` |
| `balance`, `units` | same names | `invstOrSec/{balance,units}` |
| `curCd` | `cur_cd` | `invstOrSec/curCd`, or `currencyConditional/@curCd` when exchange rate exists |
| `exchangeRt` | `exchange_rt` | `invstOrSec/currencyConditional/@exchangeRt` |
| `valUSD`, `pctVal` | `val_usd`, `pct_val` | `invstOrSec/{valUSD,pctVal}` |
| `payoffProfile` | `payoff_profile` | `invstOrSec/payoffProfile`; rule-normalized to `N/A` when `deriv_cat` is populated |
| `assetCat`, `assetConditionalDesc` | `asset_cat`, `asset_conditional_desc` | `assetCat`, or `assetConditional/@{assetCat,desc}` |
| `issuerCat`, `issuerConditionalDesc` | `issuer_cat`, `issuer_conditional_desc` | `issuerCat`, or `issuerConditional/@{issuerCat,desc}` |
| `invCountry`, `isRestrictedSec`, `fairValLevel` | `inv_country`, `is_restricted_sec`, `fair_val_level` | matching `invstOrSec` children |
| `liquidityClassificationJson`, `liquidityCircumstancesJson` | `liquidity_classification_json`, `liquidity_circumstances_json` | expands to `fundCat` or `fundCats/fundCat` plus `circumstances` |
| `isCashCollateral`, `isNonCashCollateral`, `isLoanByFund` | matching snake-case attributes | `securityLending/{isCashCollateral,isNonCashCollateral,isLoanByFund}` |
| `maturityDt`, `couponKind`, `annualizedRt`, `isDefault`, `areIntrstPmntsInArrs`, `isPaidKind` | matching snake-case attributes | `debtSec` children; the complete group is required for debt assets |
| `derivCat` | `deriv_cat` | selects one C.11 child and supplies its `@derivCat`: option/swaption/warrant, swap, forward, future, or other |
| `counterpartyName`, `counterpartyLei` | `counterparty_name`, `counterparty_lei` | selected derivative branch `counterparties/{counterpartyName,counterpartyLei}` |
| `unrealizedAppr` | `unrealized_appr` | selected derivative branch `unrealizedAppr` |
| `putOrCall`, `writtenOrPur`, `shareNo`, `exercisePrice`, `exercisePriceCurCd`, `expDt`, `delta` | matching option attributes | `optionSwaptionWarrantDeriv` children |
| `refInstType` | `ref_inst_type` | selects `descRefInstrmnt/indexBasketInfo` or `descRefInstrmnt/otherRefInst` |
| `refIndexName`, `refIndexIdentifier` | `ref_index_name`, `ref_index_identifier` | `indexBasketInfo/{indexName,indexIdentifier}` |
| `refIssuerName`, `refIssueTitle` | `ref_issuer_name`, `ref_issue_title` | `otherRefInst/{issuerName,issueTitle}` |
| `refCusip`, `refIsin`, `refTicker` | `ref_cusip`, `ref_isin`, `ref_ticker` | `otherRefInst/identifiers/{cusip,isin,ticker}/@value` |
| `swapFlag`, `terminationDt`, `upfrontPmnt`, `pmntCurCd`, `upfrontRcpt`, `rcptCurCd`, `notionalAmt`, `swapCurCd` | matching swap attributes | `swapDeriv/{swapFlag,terminationDt,upfrontPmnt,pmntCurCd,upfrontRcpt,rcptCurCd,notionalAmt,curCd}` |
| `recFixedOrFloating` | `rec_fixed_or_floating` | selects `fixedRecDesc`, `floatingRecDesc`, or `otherRecDesc` |
| `recFixedRt`, `recFloatingRtIndex`, `recFloatingRtSpread`, `recPmntAmt`, `recCurCd` | matching receive-leg attributes | attributes on the selected receive-leg element |
| `recRateTenor`, `recRateUnit`, `recResetDt`, `recResetUnit` | matching receive reset attributes | `floatingRecDesc/rtResetTenors/rtResetTenor/@{rateTenor,rateTenorUnit,resetDt,resetDtUnit}` |
| `recDesc` | `rec_desc` | text of `otherRecDesc` |
| `pmntFixedOrFloating` | `pmnt_fixed_or_floating` | selects `fixedPmntDesc`, `floatingPmntDesc`, or `otherPmntDesc` |
| `pmntFixedRt`, `pmntFloatingRtIndex`, `pmntFloatingRtSpread`, `pmntPmntAmt`, `pmntCurCdLeg` | matching payment-leg attributes | attributes on the selected payment-leg element |
| `pmntRateTenor`, `pmntRateUnit`, `pmntResetDt`, `pmntResetUnit` | matching payment reset attributes | `floatingPmntDesc/rtResetTenors/rtResetTenor` attributes |
| `pmntDesc` | `pmnt_desc` | text of `otherPmntDesc` |
| `payoffProfDeriv`, `expDt`, `notionalAmt`, `swapCurCd` | `payoff_prof_deriv`, `exp_dt`, `notional_amt`, `swap_cur_cd` | forward/future `{payOffProf,expDate,notionalAmt,curCd}` |
| `otherDerivDesc`, `terminationDt`, `notionalAmt`, `swapCurCd`, `delta` | `other_deriv_desc`, `termination_dt`, `notional_amt`, `swap_cur_cd`, `delta` | `othDeriv/@othDesc`, `terminationDt`, `notionalAmts/notionalAmt/@{amt,curCd}`, and `delta` |

## Validation ownership

| Concern | Enforced by |
|---|---|
| external names and required columns | `config.py`, `ap_orders.py`, `pipeline.py` |
| conditional holding completeness | `schema.get_required_fields` during prepare and `validate_holding` during evaluation |
| policy-derived values and applicability | `policy.py` and `preflight.py` |
| finite numeric/date/enum/JSON shape | `input_validation.py` |
| accounting and independent controls | `pipeline.evaluate_inputs` |
| XML ordering, names, namespaces, and lexical restrictions | `builder.py` followed by the bundled SEC XSD in `xsd_validator.py` |
| per-run value provenance and hashes | `field_provenance.csv`, `input_receipt.json`, and the release manifest |
