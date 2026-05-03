import { BrowserRouter, Link, NavLink, Route, Routes } from 'react-router-dom'
import ContactEditPage from './pages/ContactEditPage'
import ContactsPage from './pages/ContactsPage'
import ImportYad2Page from './pages/ImportYad2Page'
import PropertiesPage from './pages/PropertiesPage'
import PropertyEditPage from './pages/PropertyEditPage'
import QueuePage from './pages/QueuePage'
import SettingsPage from './pages/SettingsPage'
import './App.css'

export default function App() {
  return (
    <BrowserRouter>
      <header className="site-header">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            ◆
          </span>
          Classic Jerusalem Realty
        </Link>
        <nav className="site-nav" aria-label="Primary">
          <NavLink to="/" end>
            Properties
          </NavLink>
          <NavLink to="/queue">Queue</NavLink>
          <NavLink to="/contacts">Contacts</NavLink>
          <NavLink to="/import">Import from Yad2</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<PropertiesPage />} />
          <Route path="/new" element={<PropertyEditPage />} />
          <Route path="/import" element={<ImportYad2Page />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/contacts" element={<ContactsPage />} />
          <Route path="/contacts/new" element={<ContactEditPage />} />
          <Route path="/contacts/:id" element={<ContactEditPage />} />
          <Route path="/:id" element={<PropertyEditPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
