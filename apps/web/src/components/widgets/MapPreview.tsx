import { useEffect, useRef } from "react";
import L from "leaflet";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

// Vite bundles assets with hashed filenames, so leaflet's default marker
// images break unless we wire them through Vite's import system.
import iconUrl from "leaflet/dist/images/marker-icon.png";
import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";
import shadowUrl from "leaflet/dist/images/marker-shadow.png";

// Apply once on module load — leaflet caches the default icon globally.
L.Icon.Default.mergeOptions({
  iconUrl,
  iconRetinaUrl,
  shadowUrl,
});

type Props = {
  lat: number;
  lng: number;
  label?: string;
  zoom?: number;
  className?: string;
};

/**
 * Open-source map preview using react-leaflet + OpenStreetMap tiles.
 * No API key required, attribution rendered per OSM ODbL terms.
 *
 * Re-centres on lat/lng changes (e.g. when the verdict re-renders for a
 * different session) without re-mounting the whole map.
 */
export function MapPreview({
  lat,
  lng,
  label,
  zoom = 11,
  className,
}: Props) {
  return (
    <div
      className={className ?? "h-40 w-full overflow-hidden"}
      // Leaflet's container needs explicit dimensions; the parent class above
      // gives it the height. Width auto-fills.
    >
      <MapContainer
        center={[lat, lng]}
        zoom={zoom}
        scrollWheelZoom={false}
        zoomControl={false}
        attributionControl={true}
        className="h-full w-full"
      >
        <TileLayer
          // OSM standard tiles. Free, no key, ODbL-licensed.
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <Marker position={[lat, lng]}>
          {label && <Popup>{label}</Popup>}
        </Marker>
        <Recenter lat={lat} lng={lng} zoom={zoom} />
      </MapContainer>
    </div>
  );
}

/** Helper that reacts to prop changes by panning the map (no full remount). */
function Recenter({ lat, lng, zoom }: { lat: number; lng: number; zoom: number }) {
  const map = useMap();
  const last = useRef<{ lat: number; lng: number; zoom: number } | null>(null);
  useEffect(() => {
    const same =
      last.current?.lat === lat &&
      last.current?.lng === lng &&
      last.current?.zoom === zoom;
    if (!same) {
      map.setView([lat, lng], zoom, { animate: true });
      last.current = { lat, lng, zoom };
    }
  }, [lat, lng, zoom, map]);
  return null;
}
