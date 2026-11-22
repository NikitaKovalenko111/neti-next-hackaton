import { divIcon, latLngBounds, map as createMap, marker, tileLayer } from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef, useState } from 'react'
import type { MapPoint } from '../../api/messageBlocks'
import { campusMap } from '../../assets/campusMap'
import { AssistantIcon } from './AssistantIcon'

function RouteLink({ point }: { point: MapPoint }) {
  const route = new URL('https://yandex.ru/maps/')
  route.search = new URLSearchParams({
    mode: 'routes',
    rtext: `~${point.latitude},${point.longitude}`,
  }).toString()

  return (
    <a className="map-route" href={route.href} target="_blank" rel="noreferrer">
      Построить маршрут
    </a>
  )
}

function SinglePointMap({ point }: { point: MapPoint }) {
  const { latitude: lat, longitude: lon, address } = point
  const title = point.title || 'Точка на карте'
  const isMainBuilding = Math.abs(lat - 54.720714) < .00001 && Math.abs(lon - 55.933422) < .00001
  const openMap = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=17/${lat}/${lon}`
  const map = new URL('https://www.openstreetmap.org/export/embed.html')
  map.search = new URLSearchParams({
    bbox: [lon - .003, lat - .0015, lon + .003, lat + .0015].join(','),
    layer: 'mapnik',
    marker: `${lat},${lon}`,
  }).toString()

  return (
    <section className="message-map" aria-label={title}>
      <div className="map-details">
        <AssistantIcon name="pin" />
        <div>
          <strong>{title}</strong>
          {address && <p>{address}</p>}
        </div>
      </div>
      {isMainBuilding ? (
        <div className="campus-map">
          <a aria-label={`Открыть на карте · ${title}`} className="campus-map-preview" href={openMap} rel="noreferrer" target="_blank">
            <svg aria-hidden="true" viewBox="0 0 460 240" preserveAspectRatio="xMidYMid slice">
              <path className="campus-map-greenery" d={campusMap.greenery} />
              <path className="campus-map-paths" d={campusMap.paths} />
              <path className="campus-map-streets" d={campusMap.streets} />
              <path className="campus-map-buildings" d={campusMap.buildings} />
              <path className="campus-map-building" d={campusMap.mainBuilding} />
            </svg>
            <AssistantIcon name="pin" />
          </a>
          <a className="campus-map-credit" href="https://www.openstreetmap.org/copyright" rel="noreferrer" target="_blank">
            © OpenStreetMap
          </a>
        </div>
      ) : (
        <iframe loading="lazy" referrerPolicy="no-referrer" src={map.href} title={title} />
      )}
      <RouteLink point={point} />
    </section>
  )
}

function pointName(point: MapPoint, index: number) {
  return point.title || point.address || `Точка ${index + 1}`
}

function MultiPointMap({ points }: { points: MapPoint[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<ReturnType<typeof createMap> | null>(null)
  const pinsRef = useRef<{ button: HTMLButtonElement; pin: ReturnType<typeof marker> }[]>([])
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null)
  const selected = selectedIndex === null ? undefined : points[selectedIndex]

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const map = createMap(container, { scrollWheelZoom: false, zoomAnimation: false })
    mapRef.current = map
    map.attributionControl.setPrefix(false)
    tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map)

    const bounds = latLngBounds([])
    pinsRef.current = points.map((point, index) => {
      const coordinates: [number, number] = [point.latitude, point.longitude]
      const button = document.createElement('button')
      button.type = 'button'
      button.className = 'map-pin'
      button.textContent = String(index + 1)
      button.title = pointName(point, index)
      button.setAttribute('aria-label', pointName(point, index))
      button.onclick = () => setSelectedIndex(index)
      const pin = marker(coordinates, {
        icon: divIcon({ className: 'map-pin-icon', html: button, iconSize: [36, 36], iconAnchor: [18, 36] }),
        keyboard: false,
      }).addTo(map)
      bounds.extend(coordinates)
      return { button, pin }
    })

    const fitPoints = () => {
      if (!container.clientWidth || !container.clientHeight) return
      map.invalidateSize({ pan: false })
      map.fitBounds(bounds, { padding: [44, 52], maxZoom: 16, animate: false })
    }
    const resize = new ResizeObserver(fitPoints)
    resize.observe(container)
    fitPoints()

    return () => {
      resize.disconnect()
      map.remove()
      mapRef.current = null
      pinsRef.current = []
    }
  }, [points])

  useEffect(() => {
    pinsRef.current.forEach(({ button, pin }, index) => {
      const active = index === selectedIndex
      button.setAttribute('aria-pressed', String(active))
      pin.setZIndexOffset(active ? 1000 : 0)
    })
    const map = mapRef.current
    if (selected && map && map.getZoom() !== undefined) {
      map.panInside([selected.latitude, selected.longitude], { padding: [44, 52], animate: false })
    }
  }, [points, selected, selectedIndex])

  return (
    <section className="message-map" aria-label="Места на карте">
      <div className="map-details">
        <AssistantIcon name="pin" />
        <strong>Места на карте</strong>
      </div>
      <div className="map-viewport" ref={containerRef} role="group" aria-label="Карта с метками" />
      <div>
        <select
          aria-label="Выберите место для маршрута"
          className="map-point-select"
          onChange={(event) => setSelectedIndex(Number(event.target.value))}
          value={selectedIndex ?? ''}
        >
          <option disabled value="">Выберите метку или место из списка</option>
          {points.map((point, index) => (
            <option key={index} value={index}>{index + 1}. {pointName(point, index)}</option>
          ))}
        </select>
        <div aria-live="polite">
          {selected?.address && selected.address !== selected.title && <p className="map-selected-address">{selected.address}</p>}
        </div>
      </div>
      {selected && <RouteLink point={selected} />}
    </section>
  )
}

export function RouteCard({ points }: { points: MapPoint[] }) {
  if (points.length > 1) return <MultiPointMap points={points} />
  return points[0] && <SinglePointMap point={points[0]} />
}
