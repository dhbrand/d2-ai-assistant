import React, { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  Paper,
  Typography,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  LinearProgress,
  Card,
  CardContent,
  Chip,
  useTheme,
} from '@mui/material';
import {
  Search as SearchIcon,
  Sort as SortIcon,
  FilterList as FilterIcon,
} from '@mui/icons-material';

const Dashboard = () => {
  const theme = useTheme();
  const [catalysts, setCatalysts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('name');
  const [filterBy, setFilterBy] = useState('all');

  useEffect(() => {
    const fetchCatalysts = async () => {
      setLoading(true);
      try {
        const response = await fetch('https://localhost:8000/catalysts', {
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
        });
        
        if (!response.ok) {
          throw new Error(`Error fetching catalysts: ${response.status}`);
        }
        
        const data = await response.json();
        setCatalysts(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch catalysts:', err);
        setError('Failed to fetch catalysts. Please try again later.');
        setCatalysts([]);
      } finally {
        setLoading(false);
      }
    };
    
    fetchCatalysts();
  }, []);

  const filteredCatalysts = catalysts
    .filter(catalyst => {
      const matchesSearch = catalyst.name.toLowerCase().includes(searchTerm.toLowerCase());
      
      if (filterBy === 'all') return matchesSearch;
      if (filterBy === 'completed') return matchesSearch && catalyst.complete;
      if (filterBy === 'in_progress') {
        return matchesSearch && !catalyst.complete && catalyst.progress > 0;
      }
      if (filterBy === 'not_started') {
        return matchesSearch && !catalyst.complete && catalyst.progress === 0;
      }
      return matchesSearch;
    })
    .sort((a, b) => {
      if (sortBy === 'name') return a.name.localeCompare(b.name);
      if (sortBy === 'progress') return b.progress - a.progress;
      if (sortBy === 'weapon_type') return a.weaponType.localeCompare(b.weaponType);
      return 0;
    });

  const CatalystCard = ({ catalyst }) => (
    <Card
      sx={{
        mb: 2,
        background: 'rgba(13, 13, 13, 0.8)',
        backdropFilter: 'blur(10px)',
        border: '1px solid',
        borderColor: theme.palette.primary.main,
        '&:hover': {
          boxShadow: `0 0 15px ${theme.palette.primary.main}`,
        },
      }}
    >
      <CardContent>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h6">{catalyst.name}</Typography>
          <Chip
            label={catalyst.weaponType}
            color="secondary"
            size="small"
            sx={{ ml: 1 }}
          />
        </Box>

        <Typography variant="body2" color="text.secondary" gutterBottom>
          {catalyst.description}
        </Typography>

        <Box sx={{ mt: 2 }}>
          <Typography variant="body2" color="text.secondary">
            Overall Progress
          </Typography>
          <LinearProgress
            variant="determinate"
            value={catalyst.progress}
            sx={{
              mt: 1,
              height: 8,
              borderRadius: 4,
              backgroundColor: 'rgba(255, 255, 255, 0.1)',
              '& .MuiLinearProgress-bar': {
                borderRadius: 4,
              },
            }}
          />
          <Typography variant="body2" color="text.secondary" align="right" sx={{ mt: 0.5 }}>
            {Math.round(catalyst.progress)}%
          </Typography>
        </Box>

        {catalyst.objectives.map((objective, index) => (
          <Box key={index} sx={{ mt: 2 }}>
            <Typography variant="body2">
              {objective.description}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={(objective.progress / objective.completion) * 100}
              sx={{
                mt: 1,
                height: 6,
                borderRadius: 3,
                backgroundColor: 'rgba(255, 255, 255, 0.1)',
              }}
            />
            <Typography variant="body2" color="text.secondary" align="right" sx={{ mt: 0.5 }}>
              {objective.progress}/{objective.completion}
            </Typography>
          </Box>
        ))}
      </CardContent>
    </Card>
  );

  return (
    <Box>
      <Paper
        sx={{
          p: 2,
          mb: 3,
          background: 'rgba(13, 13, 13, 0.8)',
          backdropFilter: 'blur(10px)',
        }}
      >
        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} md={4}>
            <TextField
              fullWidth
              variant="outlined"
              placeholder="Search catalysts..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              InputProps={{
                startAdornment: <SearchIcon color="action" sx={{ mr: 1 }} />,
              }}
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <FormControl fullWidth>
              <InputLabel>Sort By</InputLabel>
              <Select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                startAdornment={<SortIcon color="action" sx={{ mr: 1 }} />}
              >
                <MenuItem value="name">Name</MenuItem>
                <MenuItem value="progress">Progress</MenuItem>
                <MenuItem value="weapon_type">Weapon Type</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} md={4}>
            <FormControl fullWidth>
              <InputLabel>Filter</InputLabel>
              <Select
                value={filterBy}
                onChange={(e) => setFilterBy(e.target.value)}
                startAdornment={<FilterIcon color="action" sx={{ mr: 1 }} />}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="completed">Completed</MenuItem>
                <MenuItem value="in_progress">In Progress</MenuItem>
                <MenuItem value="not_started">Not Started</MenuItem>
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      </Paper>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
          <LinearProgress sx={{ width: '100%' }} />
        </Box>
      ) : error ? (
        <Typography color="error" align="center">
          {error}
        </Typography>
      ) : (
        <Grid container spacing={3}>
          {filteredCatalysts.map((catalyst) => (
            <Grid item xs={12} md={6} lg={4} key={catalyst.recordHash}>
              <CatalystCard catalyst={catalyst} />
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
};

export default Dashboard; 