-- Create spatial index for coordinates after location table exists
CREATE INDEX IF NOT EXISTS idx_location_coords ON public.location USING gist (
    st_setsrid(
        st_makepoint(
            CAST(longitude AS float8),
            CAST(latitude AS float8)
        ),
        4326
    )
);
