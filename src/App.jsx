import { useEffect, useRef, useState } from "react";
import Globe from "react-globe.gl";

import "./App.css";

// --------------------------------------------------
// Country colors
// --------------------------------------------------

const NEIGHBOR_SHADES = [
  "rgba(56, 189, 248, 0.85)",
  "rgba(59, 130, 246, 0.70)",
  "rgba(34, 211, 238, 0.85)",
  "rgba(99, 102, 241, 0.75)",
  "rgba(14, 165, 233, 0.80)",
  "rgba(125, 211, 252, 0.90)",
  "rgba(37, 99, 235, 0.65)",
];

// --------------------------------------------------
// App
// --------------------------------------------------

function App() {
  const globeRef = useRef(null);
  const countryCache = useRef(new Map());

  const [countries, setCountries] = useState(null);
  const [movieCounts, setMovieCounts] = useState({});

  const [selectedCountry, setSelectedCountry] = useState(null);
  const [selectedMovies, setSelectedMovies] = useState([]);
  const [loadingMovies, setLoadingMovies] = useState(false);

  const [hoveredCountry, setHoveredCountry] = useState(null);
  const [countrySearch, setCountrySearch] = useState("");
  const [highlightedCountry, setHighlightedCountry] = useState(null);

  // Track window size for responsive globe resizing
  const [dimensions, setDimensions] = useState({
    width: window.innerWidth,
    height: window.innerHeight,
  });

  useEffect(() => {
    function handleResize() {
      setDimensions({
        width: window.innerWidth,
        height: window.innerHeight,
      });
    }
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // --------------------------------------------------
  // Load static data
  // --------------------------------------------------

  useEffect(() => {
    async function loadData() {
      try {
        const [countriesResponse, countsResponse] = await Promise.all([
          fetch("/data/countries.geojson"),
          fetch("/data/counts.json"),
        ]);

        if (!countriesResponse.ok) {
          throw new Error(
            `Failed to load countries.geojson (${countriesResponse.status})`,
          );
        }

        if (!countsResponse.ok) {
          throw new Error(
            `Failed to load counts.json (${countsResponse.status})`,
          );
        }

        const countriesData = await countriesResponse.json();
        const countsData = await countsResponse.json();

        if (!countriesData?.features) {
          throw new Error(
            "countries.geojson does not contain a valid features array.",
          );
        }

        setCountries(countriesData.features);
        setMovieCounts(countsData || {});
      } catch (error) {
        console.error("Data loading error:", error);
      }
    }

    loadData();
  }, []);

  // --------------------------------------------------
  // Globe renderer performance
  // --------------------------------------------------

  useEffect(() => {
    if (!globeRef.current) return;

    const renderer = globeRef.current.renderer();
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  }, [countries]);

  // --------------------------------------------------
  // Helpers
  // --------------------------------------------------

  function getISO(country) {
    const props = country?.properties || {};
    const eh = props.ISO_A2_EH;
    const a2 = props.ISO_A2;

    if (eh && eh !== "-99") return String(eh).toUpperCase();
    if (a2 && a2 !== "-99") return String(a2).toUpperCase();
    return "";
  }

  function getMovieCount(country) {
    const iso = getISO(country);
    if (!iso) return 0;
    return Number(movieCounts[iso] || 0);
  }

  function normalizeSearchText(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function getCountryName(country) {
    const props = country?.properties || {};
    return (
      props.NAME ||
      props.NAME_EN ||
      props.ADMIN ||
      props.SOVEREIGNT ||
      getISO(country) ||
      "Unknown country"
    );
  }

  function handleCountryHover(country) {
    setHoveredCountry(country || null);
  }

  function getCountryColor(country) {
    const count = getMovieCount(country);
    const countryISO = getISO(country);

    if (highlightedCountry && getISO(highlightedCountry) === countryISO) {
      return "rgba(255, 255, 255, 1)";
    }

    if (hoveredCountry && getISO(hoveredCountry) === countryISO) {
      return "rgba(255, 255, 255, 0.95)";
    }

    if (count === 0) {
      return "rgba(80, 90, 110, 0.35)";
    }

    const mapColorIndex =
      ((country.properties?.MAPCOLOR7 || 1) - 1) % NEIGHBOR_SHADES.length;

    return NEIGHBOR_SHADES[mapColorIndex];
  }

  function getCountryCenter(country) {
    const geometry = country?.geometry;
    if (!geometry) return { lat: 0, lng: 0 };

    let coordinates = [];
    if (geometry.type === "Polygon") {
      coordinates = geometry.coordinates?.[0] || [];
    } else if (geometry.type === "MultiPolygon") {
      coordinates = geometry.coordinates?.[0]?.[0] || [];
    }

    if (!coordinates.length) return { lat: 0, lng: 0 };

    let totalLng = 0;
    let totalLat = 0;

    coordinates.forEach(([lng, lat]) => {
      totalLng += lng;
      totalLat += lat;
    });

    return {
      lat: totalLat / coordinates.length,
      lng: totalLng / coordinates.length,
    };
  }

  // --------------------------------------------------
  // Country click
  // --------------------------------------------------

  async function handleCountryClick(country) {
    const iso = getISO(country);
    if (!iso) {
      console.warn("Country has no valid ISO-2 code:", country);
      return;
    }

    const countryName = getCountryName(country);
    const movieCount = getMovieCount(country);

    setSelectedCountry({
      iso,
      name: countryName,
      count: movieCount,
    });
    setHighlightedCountry(country);

    if (movieCount === 0) {
      countryCache.current.set(iso, []);
      setSelectedMovies([]);
      setLoadingMovies(false);
      return;
    }

    if (countryCache.current.has(iso)) {
      setSelectedMovies(countryCache.current.get(iso));
      setLoadingMovies(false);
      return;
    }

    setLoadingMovies(true);
    setSelectedMovies([]);

    try {
      const response = await fetch(`/data/countries/${iso}_top.json`);
      if (!response.ok) {
        throw new Error(`Failed to load ${iso}_top.json (${response.status})`);
      }

      const movies = await response.json();
      const safeMovies = Array.isArray(movies) ? movies : [];

      countryCache.current.set(iso, safeMovies);
      setSelectedMovies(safeMovies);
    } catch (error) {
      console.error(`Failed to load movies for ${iso}:`, error);
      countryCache.current.set(iso, []);
      setSelectedMovies([]);
    } finally {
      setLoadingMovies(false);
    }
  }

  // --------------------------------------------------
  // Navigate to country
  // --------------------------------------------------

  function navigateToCountry(iso) {
    if (!countries) return;

    const normalizedISO = String(iso || "")
      .toUpperCase()
      .trim();
    const country = countries.find((item) => getISO(item) === normalizedISO);

    if (!country) {
      console.warn("Country geometry not found:", normalizedISO);
      return;
    }

    setHighlightedCountry(country);

    if (globeRef.current) {
      const { lat, lng } = getCountryCenter(country);
      globeRef.current.pointOfView({ lat, lng, altitude: 1.8 }, 1000);
    }

    handleCountryClick(country);
  }

  // --------------------------------------------------
  // Country search
  // --------------------------------------------------

  const normalizedSearch = normalizeSearchText(countrySearch);

  const countrySearchResults =
    normalizedSearch.length === 0
      ? []
      : (countries || [])
          .map((country) => ({
            i: getISO(country),
            n: getCountryName(country),
            count: getMovieCount(country),
          }))
          .filter((country) => {
            if (!country.i) return false;
            const name = normalizeSearchText(country.n);
            const iso = normalizeSearchText(country.i);
            return (
              name.includes(normalizedSearch) || iso.includes(normalizedSearch)
            );
          })
          .sort((a, b) => {
            const aName = normalizeSearchText(a.n);
            const bName = normalizeSearchText(b.n);

            if (aName === normalizedSearch) return -1;
            if (bName === normalizedSearch) return 1;

            const aStarts = aName.startsWith(normalizedSearch);
            const bStarts = bName.startsWith(normalizedSearch);

            if (aStarts && !bStarts) return -1;
            if (!aStarts && bStarts) return 1;

            return aName.localeCompare(bName);
          })
          .slice(0, 8);

  // --------------------------------------------------
  // Render
  // --------------------------------------------------

  return (
    <div className="app-container">
      {/* Country Search */}
      <div className="country-search">
        <input
          type="text"
          value={countrySearch}
          onChange={(event) => setCountrySearch(event.target.value)}
          placeholder="Search country..."
          aria-label="Search country"
        />

        {countrySearchResults.length > 0 && (
          <div className="country-search-results">
            {countrySearchResults.map((country) => (
              <button
                key={country.i}
                className="country-search-result"
                onClick={() => {
                  navigateToCountry(country.i);
                  setCountrySearch("");
                }}
              >
                <span>{country.n}</span>
                <small>{country.count.toLocaleString()} movies</small>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Globe */}
      {countries && (
        <Globe
          ref={globeRef}
          width={dimensions.width}
          height={dimensions.height}
          rendererConfig={{
            antialias: false,
            alpha: true,
          }}
          showAtmosphere={false}
          hexPolygonsData={countries}
          hexPolygonResolution={3}
          hexPolygonMargin={0.3}
          hexPolygonUseDots={true}
          hexPolygonColor={getCountryColor}
          enablePointerInteraction={true}
          onHexPolygonHover={handleCountryHover}
          onHexPolygonClick={handleCountryClick}
        />
      )}

      {/* Hover Tooltip */}
      {hoveredCountry && (
        <div className="country-tooltip">
          <div className="tooltip-country">
            {getCountryName(hoveredCountry)}
          </div>
          <div className="tooltip-count">
            {getMovieCount(hoveredCountry).toLocaleString()} movies
          </div>
          <div className="tooltip-hint">Click to explore →</div>
        </div>
      )}

      {/* Country Drawer */}
      {selectedCountry && (
        <div className="country-drawer">
          <div className="drawer-handle" />

          {/* Header */}
          <div className="drawer-header">
            <div>
              <h2 className="country-name">{selectedCountry.name}</h2>
              <p className="movie-count">
                {selectedCountry.count.toLocaleString()} movies
              </p>
            </div>

            <button
              className="close-button"
              onClick={() => {
                setSelectedCountry(null);
                setSelectedMovies([]);
                setHighlightedCountry(null);
              }}
              aria-label="Close country"
            >
              ×
            </button>
          </div>

          {/* Content */}
          <div className="drawer-content">
            {loadingMovies && <div className="loading">Loading movies...</div>}

            {!loadingMovies && selectedCountry.count === 0 && (
              <div className="drawer-empty">
                <h3>No movies found</h3>
                <p>
                  There are no movies in the current dataset for this country.
                </p>
              </div>
            )}

            {!loadingMovies &&
              selectedCountry.count > 0 &&
              selectedMovies.length > 0 && (
                <>
                  {/* Top 5 Classics — Poster + Title Only */}
                  <section className="classics-section">
                    <h3>Top 5 Classics</h3>

                    <div className="classics-row">
                      {selectedMovies
                        .slice()
                        .sort((a, b) => (b.r || 0) - (a.r || 0))
                        .slice(0, 5)
                        .map((movie) => (
                          <a
                            key={movie.i}
                            href={`https://www.imdb.com/title/${movie.i}/`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="classic-card"
                          >
                            {movie.p ? (
                              <img
                                src={`https://image.tmdb.org/t/p/w185${movie.p}`}
                                alt={movie.t}
                                loading="lazy"
                              />
                            ) : (
                              <div className="poster-placeholder">
                                No Poster
                              </div>
                            )}
                            <div className="classic-title">{movie.t}</div>
                          </a>
                        ))}
                    </div>
                  </section>

                  {/* Top Movies — Clean Minimalist Rows */}
                  <section className="movies-section">
                    <h3>Top Movies</h3>

                    <div className="movie-list">
                      {selectedMovies.slice(0, 20).map((movie) => (
                        <a
                          key={movie.i}
                          href={`https://www.imdb.com/title/${movie.i}/`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="movie-card"
                        >
                          {movie.p ? (
                            <img
                              src={`https://image.tmdb.org/t/p/w185${movie.p}`}
                              alt={movie.t}
                              loading="lazy"
                            />
                          ) : (
                            <div className="movie-poster-placeholder">N/A</div>
                          )}

                          <div className="movie-info">
                            <div className="movie-title">{movie.t}</div>
                            {movie.y && (
                              <div className="movie-year">{movie.y}</div>
                            )}
                          </div>

                          <span className="movie-arrow">↗</span>
                        </a>
                      ))}
                    </div>
                  </section>
                </>
              )}

            {!loadingMovies &&
              selectedCountry.count > 0 &&
              selectedMovies.length === 0 && (
                <div className="drawer-empty">
                  <h3>No movies available</h3>
                  <p>Movie data could not be loaded for this country.</p>
                </div>
              )}
          </div>

          <div className="dataset-note">
            Data from TMDB (Nov 2026) · Not endorsed by TMDB
          </div>
        </div>
      )}

      {/* Creator Badge */}
      <a
        href="https://siddardhabvs.vercel.app/"
        target="_blank"
        rel="noopener noreferrer"
        className="creator-badge"
      >
        <img
          src="https://siddardhabvs.vercel.app/favicon.png"
          onError={(e) => {
            e.currentTarget.onerror = null;
            e.currentTarget.src =
              "https://www.google.com/s2/favicons?domain=siddardhabvs.vercel.app&sz=32";
          }}
          alt=""
          className="creator-favicon"
        />
        <span>
          Built by <strong>Siddardha</strong>{" "}
          <span className="creator-arrow">↗</span>
        </span>
      </a>
    </div>
  );
}

export default App;
