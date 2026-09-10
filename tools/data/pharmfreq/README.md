# PharmFreq metabolizer-status export (corpus #13)

Ethnogeographic metabolizer-phenotype frequencies per pharmacogene, exported from
[PharmFreq](https://pharmfreq.com/)'s "Metabolizer status tool" on 2026-09-09.

**Raw values only.** These files are committed verbatim, exactly as downloaded. The
filtering and rounding the enzyme panel applies (drop Normal Metabolizer, keep bands
above 10%, round to the nearest 10%) happen in the viewer at render time, never here
and never in the emitted data: what ships is the measurement, what the UI shows is a
reading of it.

Format: TSV, header `Subgroup / Gene / Phenotype / Frequency`, 159 data rows over 6 genes
and 8 subgroups. Frequencies sum to 1.000 per (gene, subgroup) within rounding. The
phenotype vocabulary varies per gene (CYP2B6 and CYP2C19 carry RM, CYP2C9 / CYP3A5 /
UGT1A1 carry only PM/IM/NM), and CYP3A5 has no Oceanian row.

Unlike the book corpora these files are freely downloadable and small, so they are
committed rather than kept author-side: that is what lets `check_data.py` gate the quotes
on any clone, with no skipped-and-warned path.

## Citation

Tremmel R, Zhou Y, Camara MD, Laarif S, Eliasson E, and Lauschke VM (2024) PharmFreq: a
comprehensive atlas of ethnogeographic allelic variation in clinically important
pharmacogenes. Nucleic Acids Res, pmid: 39540424, doi: 10.1093/nar/gkae1016.
