from typing import Optional

import numpy as np
import scipy.spatial.distance
import scipy.special
import scipy.stats

from ann_solo import spectrum


class SpectrumSimilarityFactory:
    def __init__(
        self, ssm: spectrum.SpectrumSpectrumMatch, top: Optional[int] = None
    ):
        """
        Instantiate the `SpectrumSimilarityFactory` to compute various spectrum
        similarities between the two spectra in the `SpectrumSpectrumMatch`.

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.
        top: Optional[int] = None
            The number of library peaks with highest intensity to consider. If
            `None`, all peaks are used.
        """
        self.ssm = ssm
        self.mz1 = ssm.query_spectrum.mz
        self.int1 = ssm.query_spectrum.intensity
        self.mz2 = ssm.library_spectrum.mz
        self.int2 = ssm.library_spectrum.intensity
        if len(ssm.peak_matches) > 0:
            self.matched_mz1 = self.mz1[ssm.peak_matches[:, 0]]
            self.matched_int1 = self.int1[ssm.peak_matches[:, 0]]
            self.matched_mz2 = self.mz2[ssm.peak_matches[:, 1]]
            self.matched_int2 = self.int2[ssm.peak_matches[:, 1]]
            # Filter the peak matches by the `top` highest intensity peaks in
            # the library spectrum.
            if top is not None:
                library_top_i = np.argpartition(self.int2, -top)[-top:]
                mask = np.isin(
                    ssm.peak_matches[:, 1], library_top_i, assume_unique=True
                )
                self.matched_mz1 = self.matched_mz1[mask]
                self.matched_int1 = self.matched_int1[mask]
                self.matched_mz2 = self.matched_mz2[mask]
                self.matched_int2 = self.matched_int2[mask]
        else:
            self.matched_mz1, self.matched_int1 = None, None
            self.matched_mz2, self.matched_int2 = None, None

    def cosine(self) -> float:
        """
        Get the cosine similarity.

        For the original description, see:
        Bittremieux, W., Meysman, P., Noble, W. S. & Laukens, K. Fast open
        modification spectral library searching through approximate nearest
        neighbor indexing. Journal of Proteome Research 17, 3463–3474 (2018).

        Returns
        -------
        float
            The cosine similarity between the two spectra.
        """
        if self.matched_int1 is not None and self.matched_int2 is not None:
            return np.dot(self.matched_int1, self.matched_int2)
        else:
            return 0.0

    def n_matched_peaks(self) -> int:
        """
        Get the number of shared peaks.

        Returns
        -------
        int
            The number of matching peaks between the two spectra.
        """
        return len(self.matched_mz1) if self.matched_mz1 is not None else 0

    def frac_n_peaks_query(self) -> float:
        """
        Get the number of shared peaks as a fraction of the number of peaks in
        the query spectrum.

        Returns
        -------
        float
            The fraction of shared peaks in the query spectrum.
        """
        if self.matched_mz1 is not None:
            return len(self.matched_mz1) / len(self.mz1)
        else:
            return 0.0

    def frac_n_peaks_library(self) -> float:
        """
        Get the number of shared peaks as a fraction of the number of peaks in
        the library spectrum.

        Returns
        -------
        float
            The fraction of shared peaks in the library spectrum.
        """
        if self.matched_mz2 is not None:
            return len(self.matched_mz2) / len(self.mz2)
        else:
            return 0.0

    def frac_intensity_query(self) -> float:
        """
        Get the fraction of explained intensity in the query spectrum.

        Returns
        -------
        float
            The fraction of explained intensity in the query spectrum.
        """
        if self.matched_int1 is not None:
            return self.matched_int1.sum() / self.int1.sum()
        else:
            return 0.0

    def frac_intensity_library(self) -> float:
        """
        Get the fraction of explained intensity in the library spectrum.

        Returns
        -------
        float
            The fraction of explained intensity in the library spectrum.
        """
        if self.matched_int2 is not None:
            return self.matched_int2.sum() / self.int2.sum()
        else:
            return 0.0

    def mean_squared_error(self, axis: str) -> float:
        """
        Get the mean squared error (MSE) of peak matches.

        Parameters
        ----------
        axis : str
            Calculate the MSE between the m/z values ("mz") or intensity values
            ("intensity") of the matched peaks.

        Returns
        -------
        float
            The MSE between the m/z or intensity values of the matched peaks in
            the two spectra.

        Raises
        ------
        ValueError
            If the specified axis is not "mz" or "intensity".
        """
        if axis == "mz":
            arr1, arr2 = self.matched_mz1, self.matched_mz2
        elif axis == "intensity":
            arr1, arr2 = self.matched_int1, self.matched_int2
        else:
            raise ValueError("Unknown axis specified")
        if arr1 is not None and arr2 is not None:
            return ((arr1 - arr2) ** 2).sum() / len(self.mz1)
        else:
            return np.inf

    def spectral_contrast_angle(self) -> float:
        """
        Get the spectral contrast angle.

        For the original description, see:
        Toprak, U. H. et al. Conserved peptide fragmentation as a benchmarking
        tool for mass spectrometers and a discriminating feature for targeted
        proteomics. Molecular & Cellular Proteomics 13, 2056–2071 (2014).

        Returns
        -------
        float
            The spectral contrast angle between the two spectra.
        """
        return 1 - 2 * np.arccos(self.cosine()) / np.pi


    def hypergeometric_score(self,min_mz: int, max_mz: int, bin_size: float) \
                            -> float:
        """
        Get the hypergeometric score of peak matches between two spectra.

        The hypergeometric score measures the probability of obtaining more than
        the observed number of peak matches by random chance, which follows a
        hypergeometric distribution.

        For the original description, see:
        Dasari, S. et al. Pepitome: Evaluating improved spectral library search for
        identification complementarity and quality assessment. Journal of Proteome
        Research 11, 1686–1695 (2012).

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The hypergeometric score of peak matches.
        """
        n_library_peaks = len(self.ssm.library_spectrum.mz)
        n_matched_peaks = len(self.ssm.peak_matches)
        n_peak_bins, _, _ = spectrum.get_dim(
            min_mz, max_mz, bin_size
        )
        return sum(
            [
                (
                    scipy.special.comb(n_library_peaks, i)
                    * scipy.special.comb(
                        n_peak_bins - n_library_peaks, n_library_peaks - i
                    )
                )
                / scipy.special.comb(n_peak_bins, n_library_peaks)
                for i in range(n_matched_peaks + 1, n_library_peaks)
            ]
        )


    def kendalltau(self) -> float:
        """
        Get the Kendall-Tau score of peak matches between two spectra.

        The Kendall-Tau score measures the correspondence between the intensity
        ranks of the set of peaks matched between spectra.

        For the original description, see:
        Dasari, S. et al. Pepitome: Evaluating improved spectral library search for
        identification complementarity and quality assessment. Journal of Proteome
        Research 11, 1686–1695 (2012).

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The hypergeometric score of peak matches.
        """
        return -1 if not len(self.ssm.peak_matches) else \
            scipy.stats.kendalltau(
            self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]],
            self.ssm.library_spectrum.intensity[self.ssm.peak_matches[:, 1]],
        )[0]


    def ms_for_id_v1(self) -> float:
        """
        Compute the MSforID (v1) similarity between two spectra.

        For the original description, see:
        Pavlic, M., Libiseller, K. & Oberacher, H. Combined use of ESI–QqTOF-MS and
        ESI–QqTOF-MS/MS with mass-spectral library search for qualitative analysis
        of drugs. Analytical and Bioanalytical Chemistry 386, 69–82 (2006).

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The MSforID (v1) similarity between both spectra.
        """
        return 0 if not len(self.ssm.peak_matches) else \
            len(self.ssm.peak_matches) ** 4 / (
                len(self.ssm.query_spectrum.mz)
                * len(self.ssm.library_spectrum.mz)
                * max(
                    np.abs(
                        self.ssm.query_spectrum.intensity[
                                                self.ssm.peak_matches[:, 0]]
                        - self.ssm.library_spectrum.intensity[
                                                self.ssm.peak_matches[:, 1]]
                    ).sum(),
                    np.finfo(float).eps,
                )
                ** 0.25
            )


    def ms_for_id_v2(self) -> float:
        """
        Compute the MSforID (v2) similarity between two spectra.

        For the original description, see:
        Oberacher, H. et al. On the inter-instrument and the inter-laboratory
        transferability of a tandem mass spectral reference library: 2.
        Optimization and characterization of the search algorithm: About an
        advanced search algorithm for tandem mass spectral reference libraries.
        Journal of Mass Spectrometry 44, 494–502 (2009).

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The MSforID (v2) similarity between both spectra.
        """
        return 0 if not len(self.ssm.peak_matches) else \
            (len(self.ssm.peak_matches) ** 4
            * (
                self.ssm.query_spectrum.intensity.sum()
                + 2 * self.ssm.library_spectrum.intensity.sum()
            )
            ** 1.25
        ) / (
            (len(self.ssm.query_spectrum.mz) + 2
             * len(self.ssm.library_spectrum.mz)) ** 2
            + np.abs(
                self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]]
                - self.ssm.library_spectrum.intensity[self.ssm.peak_matches[:, 1]]
            ).sum()
            + np.abs(
                self.ssm.query_spectrum.mz[self.ssm.peak_matches[:, 0]]
                - self.ssm.library_spectrum.mz[self.ssm.peak_matches[:, 1]]
            ).sum()
        )


    def manhattan(self) -> float:
        """
        Get the Manhattan distance between two spectra.

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The Manhattan distance between both spectra.
        """
        # Matching peaks.
        dist = np.abs(
            self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]]
            - self.ssm.library_spectrum.intensity[self.ssm.peak_matches[:, 1]]
        ).sum()
        # Unmatched peaks in the query spectrum.
        dist += self.ssm.query_spectrum.intensity[
            np.setdiff1d(
                np.arange(len(self.ssm.query_spectrum.intensity)),
                self.ssm.peak_matches[:, 0],
                assume_unique=True,
            )
        ].sum()
        # Unmatched peaks in the library spectrum.
        dist += self.ssm.library_spectrum.intensity[
            np.setdiff1d(
                np.arange(len(self.ssm.library_spectrum.intensity)),
                self.ssm.peak_matches[:, 1],
                assume_unique=True,
            )
        ].sum()
        return dist

    def euclidean(self) -> float:
        """
        Get the Euclidean distance between two spectra.

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The Euclidean distance between both spectra.
        """
        # Matching peaks.
        dist = (
                (
                    self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]]
                    - self.ssm.library_spectrum.intensity[
                        self.ssm.peak_matches[:, 1]]
                )
                ** 2
        ).sum()
        # Unmatched peaks in the query spectrum.
        dist += (
                self.ssm.query_spectrum.intensity[
                    np.setdiff1d(
                        np.arange(len(self.ssm.query_spectrum.intensity)),
                        self.ssm.peak_matches[:, 0],
                        assume_unique=True,
                    )
                ]
                ** 2
        ).sum()
        # Unmatched peaks in the library spectrum.
        dist += (
                self.ssm.library_spectrum.intensity[
                    np.setdiff1d(
                        np.arange(len(self.ssm.library_spectrum.intensity)),
                        self.ssm.peak_matches[:, 1],
                        assume_unique=True,
                    )
                ]
                ** 2
        ).sum()
        return np.sqrt(dist)

    def chebyshev(self) -> float:
        """
        Get the Chebyshev distance between two spectra.

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The Chebyshev distance between both spectra.
        """
        # Matching peaks.
        dist = np.abs(
            self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]]
            - self.ssm.library_spectrum.intensity[self.ssm.peak_matches[:, 1]]
        )
        # Unmatched peaks in the query spectrum.
        dist = np.hstack(
            (
                dist,
                self.ssm.query_spectrum.intensity[
                    np.setdiff1d(
                        np.arange(len(self.ssm.query_spectrum.intensity)),
                        self.ssm.peak_matches[:, 0],
                        assume_unique=True,
                    )
                ],
            )
        )
        # Unmatched peaks in the library spectrum.
        dist = np.hstack(
            (
                dist,
                self.ssm.library_spectrum.intensity[
                    np.setdiff1d(
                        np.arange(len(self.ssm.library_spectrum.intensity)),
                        self.ssm.peak_matches[:, 1],
                        assume_unique=True,
                    )
                ],
            )
        )
        return dist.max()

    def pearsonr(self, top: Optional[int] = None) -> float:
        """
        Get the Pearson correlation between peak matches in two spectra.

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.
        top: Optional[int] = None
            The number of library peaks with highest intensity to consider. If
            `None`, all peaks are used.

        Returns
        -------
        float
            The Pearson correlation of peak matches.
        """
        # FIXME: Use all library spectrum peaks.
        peaks_query = self.ssm.query_spectrum.intensity[
                                        self.ssm.peak_matches[:, 0]]
        peaks_library = self.ssm.library_spectrum.intensity[
                                        self.ssm.peak_matches[:, 1]]
        if top is not None:
            mask = np.isin(
                self.ssm.peak_matches[:, 1],
                np.argpartition(
                    self.ssm.library_spectrum.intensity, -top)[-top:],
                    assume_unique=True,
            )
            peaks_query, peaks_library = peaks_query[mask], peaks_library[mask]
        if len(peaks_query) > 1:
            return scipy.stats.pearsonr(peaks_query, peaks_library)[0]
        else:
            return 0.0

    def spearmanr(self, top: Optional[int] = None
    ) -> float:
        """
        Get the Spearman correlation between peak matches in two spectra.

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.
        top: Optional[int] = None
            The number of library peaks with highest intensity to consider. If
            `None`, all peaks are used.

        Returns
        -------
        float
            The Spearman correlation of peak matches.
        """
        # FIXME: Use all library spectrum peaks.
        peaks_query = self.ssm.query_spectrum.intensity[
                                        self.ssm.peak_matches[:, 0]]
        peaks_library = self.ssm.library_spectrum.intensity[
                                        self.ssm.peak_matches[:, 1]]
        if top is not None:
            mask = np.isin(
                self.ssm.peak_matches[:, 1],
                np.argpartition(
                    self.ssm.library_spectrum.intensity, -top)[-top:],
                    assume_unique=True,
            )
            peaks_query, peaks_library = peaks_query[mask], peaks_library[mask]
        if len(peaks_query) > 1:
            return scipy.stats.spearmanr(peaks_query, peaks_library)[0]
        else:
            return 0.0

    def braycurtis(self) -> float:
        """
        Get the Bray-Curtis distance between two spectra.

        The Bray-Curtis distance is defined as:

        .. math::
           \\sum{|u_i-v_i|} / \\sum{|u_i+v_i|}

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The Bray-Curtis distance between both spectra.
        """
        numerator = np.abs(
            self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]]
            - self.ssm.library_spectrum.intensity[self.ssm.peak_matches[:, 1]]
        ).sum()
        denominator = (
                self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]]
                + self.ssm.library_spectrum.intensity[self.ssm.peak_matches[:, 1]]
        ).sum()
        query_unique = self.ssm.query_spectrum.intensity[
            np.setdiff1d(
                np.arange(len(self.ssm.query_spectrum.intensity)),
                self.ssm.peak_matches[:, 0],
                assume_unique=True,
            )
        ].sum()
        library_unique = self.ssm.library_spectrum.intensity[
            np.setdiff1d(
                np.arange(len(self.ssm.library_spectrum.intensity)),
                self.ssm.peak_matches[:, 1],
                assume_unique=True,
            )
        ].sum()
        numerator += query_unique + library_unique
        denominator += query_unique + library_unique
        return numerator / denominator

    def canberra(self) -> float:
        """
        Get the Canberra distance between two spectra.

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The canberra distance between both spectra.
        """
        dist = scipy.spatial.distance.canberra(
            self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]],
            self.ssm.library_spectrum.intensity[self.ssm.peak_matches[:, 1]],
        )
        # Account for unmatched peaks in the query and library spectra.
        dist += len(self.ssm.query_spectrum.mz) - len(self.ssm.peak_matches)
        dist += len(self.ssm.library_spectrum.mz) - len(self.ssm.peak_matches)
        return dist

    def ruzicka(self) -> float:
        """
        Compute the Ruzicka similarity between two spectra.

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.

        Returns
        -------
        float
            The Ruzicka similarity between both spectra.
        """
        numerator = np.minimum(
            self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]],
            self.ssm.library_spectrum.intensity[self.ssm.peak_matches[:, 1]],
        ).sum()
        denominator = np.maximum(
            self.ssm.query_spectrum.intensity[self.ssm.peak_matches[:, 0]],
            self.ssm.library_spectrum.intensity[self.ssm.peak_matches[:, 1]],
        ).sum()
        # Account for unmatched peaks in the query and library spectra.
        denominator += self.ssm.query_spectrum.intensity[
            np.setdiff1d(
                np.arange(len(self.ssm.query_spectrum.intensity)),
                self.ssm.peak_matches[:, 0],
                assume_unique=True,
            )
        ].sum()
        denominator += self.ssm.library_spectrum.intensity[
            np.setdiff1d(
                np.arange(len(self.ssm.library_spectrum.intensity)),
                self.ssm.peak_matches[:, 1],
                assume_unique=True,
            )
        ].sum()
        return numerator / denominator

    def scribe_fragment_acc(self, top: Optional[int] = None) -> float:
        """
        Get the Scribe fragmentation accuracy between two spectra.

        For the original description, see:
        Searle, B. C. et al. Scribe: next-generation library searching for DDA
        experiments. ASMS 2022.

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.
        top: Optional[int] = None
            The number of library peaks with highest intensity to consider. If
            `None`, all peaks are used.

        Returns
        -------
        float
            The Scribe fragmentation accuracy between both spectra.
        """
        # FIXME: Use all library spectrum peaks.
        peaks_query = self.ssm.query_spectrum.intensity[
                                                self.ssm.peak_matches[:, 0]]
        peaks_library = self.ssm.library_spectrum.intensity[
                                                self.ssm.peak_matches[:, 1]]
        if top is not None:
            mask = np.isin(
                self.ssm.peak_matches[:, 1],
                np.argpartition(
                    self.ssm.library_spectrum.intensity, -top)[-top:],
                    assume_unique=True,
            )
            peaks_query, peaks_library = peaks_query[mask], peaks_library[mask]
        return np.log(
            1
            / max(
                0.001,  # Guard against infinity for identical spectra.
                (
                        (
                                peaks_query / peaks_query.sum()
                                - peaks_library / peaks_library.sum()
                        )
                        ** 2
                ).sum(),
            ),
        )

    def entropy(self, weighted: bool = False) -> float:
        """
        Get the entropy between two spectra.

        For the original description, see:
        Li, Y. et al. Spectral entropy outperforms MS/MS dot product similarity for
        small-molecule compound identification. Nature Methods 18, 1524–1531
        (2021).

        Parameters
        ----------
        ssm : spectrum.SpectrumSpectrumMatch
            The match between a query spectrum and a library spectrum.
        weighted : bool
            Whether to use the unweighted or weighted version of entropy.

        Returns
        -------
        float
            The entropy between both spectra.
        """
        query_entropy = _spectrum_entropy(self.ssm.query_spectrum.intensity,
                                          weighted)
        library_entropy = _spectrum_entropy(
            self.ssm.library_spectrum.intensity, weighted
        )
        merged_entropy = _spectrum_entropy(_merge_entropy(self.ssm), weighted)
        return 2 * merged_entropy - query_entropy - library_entropy

def _spectrum_entropy(
    spectrum_intensity: np.ndarray, weighted: bool = False
) -> float:
    """
    Compute the entropy of a spectrum from its peak intensities.

    Parameters
    ----------
    spectrum_intensity : np.ndarray
        The intensities of the spectrum peaks.
    weighted : bool
        Whether to use the unweighted or weighted version of entropy.

    Returns
    -------
    float
        The entropy of the given spectrum.
    """
    weight_start, entropy_cutoff = 0.25, 3
    weight_slope = (1 - weight_start) / entropy_cutoff
    spec_entropy = scipy.stats.entropy(spectrum_intensity)
    if not weighted or spec_entropy > entropy_cutoff:
        return spec_entropy
    else:
        weight = weight_start + weight_slope * spec_entropy
        weighted_intensity = spectrum_intensity**weight
        weighted_intensity /= weighted_intensity.sum()
        return scipy.stats.entropy(weighted_intensity)


def _merge_entropy(ssm: spectrum.SpectrumSpectrumMatch) -> np.ndarray:
    """
    Merge two spectra prior to entropy calculation of the spectrum-spectrum
    match.

    Parameters
    ----------
    ssm : spectrum.SpectrumSpectrumMatch
        The match between a query spectrum and a library spectrum.

    Returns
    -------
    np.ndarray
        NumPy array with the intensities of the merged peaks summed.
    """
    # Initialize with the query spectrum peaks.
    merged = ssm.query_spectrum.intensity.copy()
    # Sum the intensities of matched peaks.
    merged[ssm.peak_matches[:, 0]] += ssm.library_spectrum.intensity[
        ssm.peak_matches[:, 1]
    ]
    # Append the unmatched library spectrum peaks.
    merged = np.hstack(
        (
            merged,
            ssm.library_spectrum.intensity[
                np.setdiff1d(
                    np.arange(len(ssm.library_spectrum.intensity)),
                    ssm.peak_matches[:, 1],
                    assume_unique=True,
                )
            ],
        )
    )
    return merged
