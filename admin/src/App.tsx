import { BrowserRouter, Link, NavLink, Route, Routes } from 'react-router-dom'
import ContactEditPage from './pages/ContactEditPage'
import ContactImportPage from './pages/ContactImportPage'
import ContactsPage from './pages/ContactsPage'
import GroupsPage from './pages/GroupsPage'
import ImportYad2Page from './pages/ImportYad2Page'
import NewsletterPage from './pages/NewsletterPage'
import PropertiesPage from './pages/PropertiesPage'
import PropertyEditPage from './pages/PropertyEditPage'
import QueuePage from './pages/QueuePage'
import SettingsPage from './pages/SettingsPage'
import SystemPage from './pages/SystemPage'
import WhatsappThreadsPage from './pages/WhatsappThreadsPage'
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
          <NavLink to="/groups">Groups</NavLink>
          <NavLink to="/contacts">Contacts</NavLink>
          <NavLink to="/newsletter">Newsletter</NavLink>
          <NavLink to="/chatbot">Chatbot</NavLink>
          <NavLink to="/import">Import from Yad2</NavLink>
          <NavLink to="/settings">Settings</NavLink>
          <NavLink to="/system">System</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<PropertiesPage />} />
          <Route path="/new" element={<PropertyEditPage />} />
          <Route path="/import" element={<ImportYad2Page />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/queue" element={<QueuePage />} />
          <Route path="/groups" element={<GroupsPage />} />
          <Route path="/contacts" element={<ContactsPage />} />
          <Route path="/contacts/import" element={<ContactImportPage />} />
          <Route path="/contacts/new" element={<ContactEditPage />} />
          <Route path="/contacts/:id" element={<ContactEditPage />} />
          <Route path="/newsletter" element={<NewsletterPage />} />
          <Route path="/chatbot" element={<WhatsappThreadsPage />} />
          <Route path="/system" element={<SystemPage />} />
          <Route path="/:id" element={<PropertyEditPage />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
