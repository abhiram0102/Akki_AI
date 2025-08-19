import { Switch, Route } from "wouter";
import NotFound from "@/pages/not-found";
import Login from "@/pages/login";
import Dashboard from "@/pages/dashboard";
import CodingPage from "@/pages/coding";
import RedTeamPage from "@/pages/redteam";
import OSINTPage from "@/pages/osint";
import ReportsPage from "@/pages/reports";

function AppWrapper() {
  return (
    <Switch>
      <Route path="/login" component={Login} />
      <Route path="/coding" component={CodingPage} />
      <Route path="/redteam" component={RedTeamPage} />
      <Route path="/osint" component={OSINTPage} />
      <Route path="/reports" component={ReportsPage} />
      <Route path="/" component={Dashboard} />
      <Route component={NotFound} />
    </Switch>
  );
}

export default AppWrapper;
