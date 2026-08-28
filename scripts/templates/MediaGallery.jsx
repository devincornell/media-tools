import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import './MediaGallery.css';

export default function MediaGallery({
  pageName = 'Root',
  name = 'Media Gallery',
  subpages = [],
  vids = [],
  clips = [],
  images = []
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [viewMode, setViewMode] = useState('grid');
  const [zoomLevel, setZoomLevel] = useState(250);
  const [category, setCategory] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [sortOption, setSortOption] = useState('');
  
  const [favorites, setFavorites] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('mediaFavorites') || '[]');
    } catch {
      return [];
    }
  });

  const [toastMessage, setToastMessage] = useState('');
  const [showToast, setShowToast] = useState(false);
  const [showScrollTop, setShowScrollTop] = useState(false);

  // Help Modal
  const [helpOpen, setHelpOpen] = useState(false);

  // Video Player
  const [playerOpen, setPlayerOpen] = useState(false);
  const [currentVideo, setCurrentVideo] = useState(null);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [autoplay, setAutoplay] = useState(() => localStorage.getItem('videoAutoplay') === 'true');
  const [playlistCollapsed, setPlaylistCollapsed] = useState(false);
  const [countdownActive, setCountdownActive] = useState(false);
  const [countdownTime, setCountdownTime] = useState(3);
  
  const videoRef = useRef(null);
  const countdownIntervalRef = useRef(null);

  // Lightbox
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [currentImage, setCurrentImage] = useState(null);

  // --- Effects & Listeners ---
  useEffect(() => {
    localStorage.setItem('mediaFavorites', JSON.stringify(favorites));
  }, [favorites]);

  useEffect(() => {
    localStorage.setItem('videoAutoplay', autoplay);
  }, [autoplay]);

  useEffect(() => {
    const handleScroll = () => setShowScrollTop(window.scrollY > 300);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const allVideosAndClips = useMemo(() => [...vids, ...clips], [vids, clips]);

  const openPlayer = useCallback((vid) => {
    cancelAutoplay();
    setCurrentVideo(vid);
    setPlayerOpen(true);
    document.body.style.overflow = 'hidden';
  }, []);

  const closePlayer = useCallback(() => {
    setPlayerOpen(false);
    if (videoRef.current) videoRef.current.pause();
    cancelAutoplay();
    document.body.style.overflow = 'auto';
    setCurrentVideo(null);
  }, []);

  const navigateVideo = useCallback((direction) => {
    if (!currentVideo) return;
    const currentIndex = allVideosAndClips.findIndex(v => v.vid_path_rel === currentVideo.vid_path_rel);
    if (currentIndex === -1) return;
    
    let nextIndex;
    if (direction === -1) {
      nextIndex = (currentIndex - 1 + allVideosAndClips.length) % allVideosAndClips.length;
    } else {
      nextIndex = (currentIndex + 1) % allVideosAndClips.length;
    }
    openPlayer(allVideosAndClips[nextIndex]);
  }, [currentVideo, allVideosAndClips, openPlayer]);

  const displayToast = (msg) => {
    setToastMessage(msg);
    setShowToast(true);
    setTimeout(() => setShowToast(false), 3000);
  };

  const cancelAutoplay = useCallback(() => {
    setCountdownActive(false);
    if (countdownIntervalRef.current) clearInterval(countdownIntervalRef.current);
  }, []);

  const proceedToNextVideo = useCallback((nextIndex) => {
    cancelAutoplay();
    if (nextIndex !== undefined) {
      openPlayer(allVideosAndClips[nextIndex]);
    } else {
      navigateVideo(1);
    }
  }, [allVideosAndClips, openPlayer, navigateVideo, cancelAutoplay]);

  const handleVideoEnd = useCallback(() => {
    if (autoplay) {
      const currentIndex = allVideosAndClips.findIndex(v => v.vid_path_rel === currentVideo?.vid_path_rel);
      if (currentIndex !== -1 && currentIndex < allVideosAndClips.length - 1) {
        setCountdownTime(3);
        setCountdownActive(true);
        countdownIntervalRef.current = setInterval(() => {
          setCountdownTime(prev => {
            if (prev <= 1) {
              clearInterval(countdownIntervalRef.current);
              proceedToNextVideo(currentIndex + 1);
              return 0;
            }
            return prev - 1;
          });
        }, 1000);
      }
    }
  }, [autoplay, allVideosAndClips, currentVideo, proceedToNextVideo]);

  const navigateImage = useCallback((direction) => {
    if (!currentImage) return;
    const currentIndex = images.findIndex(img => img.img_path_rel === currentImage.img_path_rel);
    if (currentIndex === -1) return;
    
    let nextIndex;
    if (direction === -1) {
      nextIndex = (currentIndex - 1 + images.length) % images.length;
    } else {
      nextIndex = (currentIndex + 1) % images.length;
    }
    setCurrentImage(images[nextIndex]);
  }, [currentImage, images]);

  const closeLightbox = useCallback(() => {
    setLightboxOpen(false);
    document.body.style.overflow = 'auto';
    setCurrentImage(null);
  }, []);

  const handleSpeedChange = (speed) => {
    setPlaybackRate(speed);
    if (videoRef.current) videoRef.current.playbackRate = speed;
  };

  const toggleFullScreen = () => {
    const container = document.querySelector('.video-container');
    if (!document.fullscreenElement) {
      container?.requestFullscreen().catch(console.error);
    } else {
      document.exitFullscreen();
    }
  };

  const togglePiP = async () => {
    if (document.pictureInPictureElement) {
      await document.exitPictureInPicture();
    } else if (videoRef.current?.requestPictureInPicture) {
      await videoRef.current.requestPictureInPicture();
    }
  };

  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ignore if typing in input
      if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;

      if (e.key === '?') {
        setHelpOpen(true);
        e.preventDefault();
        return;
      }
      if (e.key === 'Escape') {
        if (countdownActive) {
          cancelAutoplay();
          return;
        }
        setHelpOpen(false);
        closePlayer();
        closeLightbox();
        return;
      }

      if (lightboxOpen && currentImage) {
        if (e.key === 'ArrowLeft') navigateImage(-1);
        if (e.key === 'ArrowRight') navigateImage(1);
        return;
      }

      if (playerOpen) {
        if (e.code === 'Space') {
          if (videoRef.current) {
            videoRef.current.paused ? videoRef.current.play() : videoRef.current.pause();
          }
          e.preventDefault();
        } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
          if (e.shiftKey) {
            const newSpeed = e.key === 'ArrowUp' 
              ? Math.min(playbackRate + 0.25, 4) 
              : Math.max(playbackRate - 0.25, 0.25);
            handleSpeedChange(newSpeed);
          } else if (videoRef.current) {
            const currentVol = videoRef.current.volume;
            videoRef.current.volume = e.key === 'ArrowUp' 
              ? Math.min(currentVol + 0.1, 1) 
              : Math.max(currentVol - 0.1, 0);
            displayToast(`Volume: ${Math.round(videoRef.current.volume * 100)}%`);
          }
          e.preventDefault();
        } else if (e.key === 'f' || e.key === 'F') {
          toggleFullScreen();
          e.preventDefault();
        } else if (e.key === 'p' || e.key === 'P') {
          togglePiP();
          e.preventDefault();
        } else if (e.key === 'm' || e.key === 'M') {
          if (videoRef.current) {
            videoRef.current.muted = !videoRef.current.muted;
            displayToast(videoRef.current.muted ? 'Muted' : 'Unmuted');
          }
          e.preventDefault();
        } else if (e.key === 'ArrowLeft') {
          navigateVideo(-1);
          e.preventDefault();
        } else if (e.key === 'ArrowRight') {
          navigateVideo(1);
          e.preventDefault();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [countdownActive, lightboxOpen, playerOpen, currentImage, playbackRate, navigateImage, navigateVideo, cancelAutoplay, closePlayer, closeLightbox]);

  // --- Handlers ---
  const copyLink = (e, path) => {
    e.preventDefault();
    e.stopPropagation();
    const url = window.location.origin + '/' + path;
    navigator.clipboard.writeText(url).then(() => displayToast('Link copied to clipboard!'));
  };

  const toggleFavorite = (e, path) => {
    e.preventDefault();
    e.stopPropagation();
    if (favorites.includes(path)) {
      setFavorites(favorites.filter(f => f !== path));
      displayToast('Removed from favorites');
    } else {
      setFavorites([...favorites, path]);
      displayToast('Added to favorites');
    }
  };

  const openLightbox = (e, img) => {
    e.preventDefault();
    setCurrentImage(img);
    setLightboxOpen(true);
    document.body.style.overflow = 'hidden';
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '0:00';
    const s = parseFloat(seconds);
    const m = Math.floor(s / 60);
    const rs = Math.floor(s % 60);
    return `${m}:${rs.toString().padStart(2, '0')}`;
  };

  const scrollToTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });

  // --- Filtering & Sorting Data ---
  const filterMedia = (items, typeKey, pathKey) => {
    return items.filter(item => {
      const nameMatch = (item.name || item.vid_title || item.title || '').toLowerCase().includes(searchTerm.toLowerCase());
      const path = item[pathKey] ? `${typeKey === 'folder' ? 'page' : typeKey === 'image' ? 'file' : 'video'}/${item[pathKey]}` : '';
      const isFav = favorites.includes(path);
      const catMatch = category === 'all' || (category === 'favorites' ? isFav : category === typeKey);
      return nameMatch && catMatch;
    });
  };

  const sortItems = (items) => {
    if (!sortOption) return items;
    return [...items].sort((a, b) => {
      const aName = a.name || a.vid_title || a.title || '';
      const bName = b.name || b.vid_title || b.title || '';
      if (sortOption === 'name-asc') return aName.localeCompare(bName);
      if (sortOption === 'name-desc') return bName.localeCompare(aName);
      
      const aDur = parseFloat(a.duration || 0);
      const bDur = parseFloat(b.duration || 0);
      if (sortOption === 'duration-asc') return aDur - bDur;
      if (sortOption === 'duration-desc') return bDur - aDur;
      
      return 0;
    });
  };

  const processedFolders = filterMedia(subpages, 'folder', 'page_path_rel').map(f => ({...f, fullPath: `page/${f.page_path_rel}`}));
  const processedVids = sortItems(filterMedia(vids, 'video', 'vid_path_rel')).map(v => ({...v, fullPath: `video/${v.vid_path_rel}`}));
  const processedClips = sortItems(filterMedia(clips, 'clip', 'vid_path_rel')).map(c => ({...c, fullPath: `video/${c.vid_path_rel}`}));
  const processedImages = filterMedia(images, 'image', 'img_path_rel').map(i => ({...i, fullPath: `file/${i.img_path_rel}`}));

  const gridStyle = viewMode === 'grid' ? { gridTemplateColumns: `repeat(auto-fill, minmax(${zoomLevel}px, 1fr))` } : {};

  return (
    <>
      <button className="mobile-menu-toggle" onClick={() => setSidebarOpen(!sidebarOpen)}>
        <i className="fas fa-bars"></i>
      </button>

      <div className={`sidebar ${sidebarOpen ? 'open' : ''}`} id="sidebar">
        <div className="sidebar-header">
          <h2><i className="fas fa-photo-video"></i></h2>
        </div>
        <nav className="sidebar-nav">
          <div className="nav-item">
            <a href={`../${pageName}`} className="nav-link" title="Go up"><i className="fas fa-level-up-alt"></i></a>
          </div>
          <div className="nav-item">
            <a href="/" className="nav-link" title="Home"><i className="fas fa-home"></i></a>
          </div>
          <div className="nav-item">
            <a href="/list_directories" className="nav-link" title="List directories"><i className="fas fa-list"></i></a>
          </div>
          <div className="nav-item">
            <a href="/list_videos" className="nav-link" title="List videos"><i className="fas fa-play-circle"></i></a>
          </div>
          <div className="nav-item">
            <a href="/update" className="nav-link" title="Update library"><i className="fas fa-sync-alt"></i></a>
          </div>
          <div className="nav-item">
            <a href="#folders" className="nav-link" title="Folders"><i className="fas fa-folder"></i></a>
          </div>
          <div className="nav-item">
            <a href="#videos" className="nav-link" title="Videos"><i className="fas fa-video"></i></a>
          </div>
          <div className="nav-item">
            <a href="#images" className="nav-link" title="Images"><i className="fas fa-image"></i></a>
          </div>
        </nav>
      </div>

      <div className="main-container">
        <div className="header fade-in">
          <h1>{name}</h1>
        </div>

        <div className="search-filter-bar fade-in">
          <div className="search-box">
            <i className="fas fa-search search-icon"></i>
            <input 
              type="search" 
              className="search-input" 
              placeholder="Search media files..." 
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
            />
          </div>
          
          <div className="category-filters">
            <button className={`filter-btn ${category === 'all' ? 'active' : ''}`} onClick={() => setCategory('all')}>All</button>
            <button className={`filter-btn ${category === 'favorites' ? 'active' : ''}`} onClick={() => setCategory('favorites')}><i className="fas fa-heart"></i></button>
            <button className={`filter-btn ${category === 'folder' ? 'active' : ''}`} onClick={() => setCategory('folder')}><i className="fas fa-folder"></i></button>
            <button className={`filter-btn ${category === 'video' ? 'active' : ''}`} onClick={() => setCategory('video')}><i className="fas fa-video"></i></button>
            <button className={`filter-btn ${category === 'clip' ? 'active' : ''}`} onClick={() => setCategory('clip')}><i className="fas fa-cut"></i></button>
            <button className={`filter-btn ${category === 'image' ? 'active' : ''}`} onClick={() => setCategory('image')}><i className="fas fa-image"></i></button>
          </div>

          <div className="sort-controls">
            <select className="sort-select" value={sortOption} onChange={e => setSortOption(e.target.value)}>
              <option value="">Sort by...</option>
              <option value="name-asc">Name (A-Z)</option>
              <option value="name-desc">Name (Z-A)</option>
              <option value="duration-asc">Duration (Short-Long)</option>
              <option value="duration-desc">Duration (Long-Short)</option>
            </select>
          </div>
          
          <div className="zoom-controls" style={{display: 'flex', alignItems: 'center', gap: '0.5rem', marginLeft: 'auto'}}>
            <i className="fas fa-image" style={{color: 'var(--text-muted)', fontSize: '0.8rem'}}></i>
            <input 
              type="range" 
              min="150" max="400" 
              value={zoomLevel} 
              onChange={e => setZoomLevel(e.target.value)}
              className="zoom-slider" 
              title="Thumbnail Size" 
            />
            <i className="fas fa-image" style={{color: 'var(--text-muted)', fontSize: '1.2rem'}}></i>
          </div>

          <div className="view-toggle">
            <button className={`view-btn ${viewMode === 'grid' ? 'active' : ''}`} onClick={() => setViewMode('grid')}>
              <i className="fas fa-th"></i>
            </button>
            <button className={`view-btn ${viewMode === 'list' ? 'active' : ''}`} onClick={() => setViewMode('list')}>
              <i className="fas fa-list"></i>
            </button>
          </div>
          
          <button className="view-btn" onClick={() => setHelpOpen(true)} style={{background: 'var(--bg-tertiary)', border: '1px solid var(--border-color)', borderRadius: '8px', minWidth: '42px', minHeight: '38px', padding: '0.5rem 0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', marginLeft: '0.5rem'}}>
            <i className="fas fa-keyboard" style={{color: 'var(--text-secondary)'}}></i>
          </button>
        </div>

        {/* Folders */}
        {processedFolders.length > 0 && (
          <div className="gallery-section fade-in">
            <h2 className="section-title" id="folders">
              <i className="fas fa-folder-open"></i> Folders ({processedFolders.length})
            </h2>
            <div className={`gallery ${viewMode === 'list' ? 'list-view' : ''}`} style={gridStyle}>
              {processedFolders.map((cp, idx) => {
                const thumbSrc = cp.subfolder_thumbs_all?.length 
                  ? `/thumb/${cp.subfolder_thumbs_all[Math.floor(Math.random() * cp.subfolder_thumbs_all.length)]}`
                  : `/file/${cp.subfolder_thumb}`;

                return (
                  <div key={idx} className="thumbnail" data-type="folder">
                    <div className="thumbnail-actions-overlay">
                      <button className={`icon-btn fav-btn ${favorites.includes(cp.fullPath) ? 'active' : ''}`} onClick={(e) => toggleFavorite(e, cp.fullPath)}>
                        <i className={favorites.includes(cp.fullPath) ? 'fas fa-heart' : 'far fa-heart'}></i>
                      </button>
                      <button className="icon-btn" onClick={(e) => copyLink(e, cp.fullPath)}><i className="fas fa-link"></i></button>
                    </div>
                    <a href={`/${cp.fullPath}`} style={{textDecoration: 'none', color: 'inherit'}}>
                      <img src={thumbSrc} loading="lazy" alt={`${cp.name} folder`} />
                      <div className="thumbnail-content">
                        <div className="thumbnail-title">{cp.name}</div>
                        <div className="thumbnail-info">
                          <i className="fas fa-video"></i> {cp.num_vids} videos<br/>
                          <i className="fas fa-folder"></i> {cp.num_subfolders} folders<br/>
                          <i className="fas fa-hdd"></i> {cp.files_size_str} total
                        </div>
                      </div>
                    </a>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Videos */}
        {processedVids.length > 0 && (
          <div className="gallery-section fade-in">
            <h2 className="section-title" id="videos">
              <i className="fas fa-video"></i> Videos ({processedVids.length})
            </h2>
            <div className={`gallery ${viewMode === 'list' ? 'list-view' : ''}`} style={gridStyle}>
              {processedVids.map((vid, idx) => (
                <div key={idx} className="thumbnail" onClick={() => openPlayer(vid)}>
                  <div className="thumbnail-actions-overlay">
                    <button className={`icon-btn fav-btn ${favorites.includes(vid.fullPath) ? 'active' : ''}`} onClick={(e) => { e.stopPropagation(); toggleFavorite(e, vid.fullPath); }}>
                      <i className={favorites.includes(vid.fullPath) ? 'fas fa-heart' : 'far fa-heart'}></i>
                    </button>
                    <button className="icon-btn" onClick={(e) => { e.stopPropagation(); copyLink(e, vid.fullPath); }}><i className="fas fa-link"></i></button>
                  </div>
                  <img src={`/thumb/${vid.hash}.gif`} loading="lazy" alt={`Preview of ${vid.vid_title}`} />
                  <div className="thumbnail-content">
                    <div className="thumbnail-title">{vid.vid_title}</div>
                    <div className="thumbnail-info">
                      <i className="fas fa-clock"></i> {vid.duration_str}<br/>
                      <i className="fas fa-hdd"></i> {vid.vid_size_str}<br/>
                      <i className="fas fa-expand"></i> {vid.res_str}<br/>
                      <i className="fas fa-calendar-alt"></i> {vid.created}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Clips */}
        {processedClips.length > 0 && (
          <div className="gallery-section fade-in">
            <h2 className="section-title" id="clips">
              <i className="fas fa-cut"></i> Clips ({processedClips.length})
            </h2>
            <div className={`gallery ${viewMode === 'list' ? 'list-view' : ''}`} style={gridStyle}>
              {processedClips.map((clip, idx) => (
                <div key={idx} className="thumbnail" onClick={() => openPlayer(clip)}>
                  <div className="thumbnail-actions-overlay">
                    <button className={`icon-btn fav-btn ${favorites.includes(clip.fullPath) ? 'active' : ''}`} onClick={(e) => { e.stopPropagation(); toggleFavorite(e, clip.fullPath); }}>
                      <i className={favorites.includes(clip.fullPath) ? 'fas fa-heart' : 'far fa-heart'}></i>
                    </button>
                    <button className="icon-btn" onClick={(e) => { e.stopPropagation(); copyLink(e, clip.fullPath); }}><i className="fas fa-link"></i></button>
                  </div>
                  <img src={`/thumb/${clip.hash}.gif`} loading="lazy" alt={`Preview of ${clip.vid_title}`} />
                  <div className="thumbnail-content">
                    <div className="thumbnail-title">{clip.vid_title}</div>
                    <div className="thumbnail-info">
                      <i className="fas fa-clock"></i> {clip.duration_str}<br/>
                      <i className="fas fa-hdd"></i> {clip.vid_size_str}<br/>
                      <i className="fas fa-expand"></i> {clip.res_str}<br/>
                      <i className="fas fa-calendar-alt"></i> {clip.created}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Images */}
        {processedImages.length > 0 && (
          <div className="gallery-section fade-in">
            <h2 className="section-title" id="images">
              <i className="fas fa-image"></i> Images ({processedImages.length})
            </h2>
            <div className={`gallery ${viewMode === 'list' ? 'list-view' : ''}`} style={gridStyle}>
              {processedImages.map((img, idx) => (
                <div key={idx} className="thumbnail">
                  <div className="thumbnail-actions-overlay">
                    <button className={`icon-btn fav-btn ${favorites.includes(img.fullPath) ? 'active' : ''}`} onClick={(e) => { e.stopPropagation(); toggleFavorite(e, img.fullPath); }}>
                      <i className={favorites.includes(img.fullPath) ? 'fas fa-heart' : 'far fa-heart'}></i>
                    </button>
                    <button className="icon-btn" onClick={(e) => { e.stopPropagation(); copyLink(e, img.fullPath); }}><i className="fas fa-link"></i></button>
                  </div>
                  <a href={`/${img.fullPath}`} onClick={(e) => openLightbox(e, img)}>
                    <img src={`/${img.fullPath}`} loading="lazy" alt={img.title || 'Image'} />
                  </a>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Video Player Modal */}
      {playerOpen && currentVideo && (
        <div className="video-player" style={{display: 'block'}} onClick={(e) => e.target.classList.contains('player-container') && closePlayer()}>
          <div className="player-container">
            <button className="player-close" onClick={closePlayer}><i className="fas fa-times"></i></button>
            
            {countdownActive && (
              <div className="autoplay-countdown" style={{display: 'block'}}>
                <div>Next video starting in</div>
                <div className="countdown-number">{countdownTime}</div>
                <div className="countdown-actions">
                  <button className="countdown-btn" onClick={() => proceedToNextVideo()}>Play Now</button>
                  <button className="countdown-btn secondary" onClick={cancelAutoplay}>Cancel</button>
                </div>
              </div>
            )}
            
            <div className="player-info">
              <h2 className="player-title">{currentVideo.vid_title}</h2>
              <p className="player-details">{currentVideo.duration_str} | {currentVideo.vid_size_str} | {currentVideo.res_str}</p>
            </div>
            
            <div className="player-main">
              <div className="video-container">
                <video 
                  ref={videoRef}
                  controls 
                  className="player-video" 
                  autoPlay 
                  onEnded={handleVideoEnd}
                  src={`/video/${currentVideo.vid_path_rel}`}
                />
                
                <div className="player-controls">
                  <button className="nav-btn" onClick={() => navigateVideo(-1)}><i className="fas fa-chevron-left"></i></button>
                  
                  <select className="speed-control" value={playbackRate} onChange={(e) => handleSpeedChange(parseFloat(e.target.value))}>
                    {[0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4].map(rate => (
                      <option key={rate} value={rate}>{rate}×</option>
                    ))}
                  </select>
                  
                  <div className="autoplay-control">
                    <label className="autoplay-label">
                      <input type="checkbox" checked={autoplay} onChange={e => setAutoplay(e.target.checked)} className="autoplay-checkbox" />
                      <span className="autoplay-text"><i className="fas fa-play-circle"></i> Auto-play next</span>
                    </label>
                  </div>
                  
                  <button className="nav-btn" onClick={() => navigateVideo(1)}><i className="fas fa-chevron-right"></i></button>
                  <button className="nav-btn" onClick={toggleFullScreen}><i className="fas fa-expand"></i></button>
                  <button className="nav-btn" onClick={togglePiP}><i className="fas fa-external-link-square-alt"></i></button>
                  
                  <a href={`/video/${currentVideo.vid_path_rel}`} download className="action-btn">
                    <i className="fas fa-download"></i> Download
                  </a>
                  <a href={`/video/${currentVideo.vid_path_rel}`} target="_blank" rel="noreferrer" className="action-btn secondary">
                    <i className="fas fa-external-link-alt"></i> Open
                  </a>
                </div>
              </div>
              
              <div className={`video-playlist ${playlistCollapsed ? 'collapsed' : ''}`}>
                <div className="playlist-header">
                  <h3>Playlist</h3>
                  <button className="playlist-toggle" onClick={() => setPlaylistCollapsed(!playlistCollapsed)}>
                    <i className={`fas fa-chevron-${playlistCollapsed ? 'left' : 'right'}`}></i>
                  </button>
                </div>
                <div className="playlist-content">
                  {allVideosAndClips.map((v, i) => (
                    <div 
                      key={i} 
                      className={`playlist-item ${currentVideo.vid_path_rel === v.vid_path_rel ? 'active' : ''}`}
                      onClick={() => openPlayer(v)}
                    >
                      <img src={`/thumb/${v.hash}.gif`} className="playlist-thumbnail" loading="lazy" alt="" />
                      <div className="playlist-info">
                        <div className="playlist-title">{v.vid_title}</div>
                        <div className="playlist-duration">{formatDuration(v.duration)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Image Lightbox */}
      {lightboxOpen && currentImage && (
        <div className="video-player" style={{display: 'block'}} onClick={(e) => e.target.classList.contains('player-container') && closeLightbox()}>
          <div className="player-container">
            <button className="player-close" onClick={closeLightbox}><i className="fas fa-times"></i></button>
            <div className="image-nav-controls">
              <button className="nav-btn image-nav-btn" onClick={(e) => { e.stopPropagation(); navigateImage(-1); }}><i className="fas fa-chevron-left"></i></button>
              <button className="nav-btn image-nav-btn" onClick={(e) => { e.stopPropagation(); navigateImage(1); }}><i className="fas fa-chevron-right"></i></button>
            </div>
            <img src={`/${currentImage.fullPath}`} className="player-video" alt="" onClick={e => e.stopPropagation()} />
          </div>
        </div>
      )}

      {/* Help Modal */}
      {helpOpen && (
        <div className="video-player" style={{display: 'flex', alignItems: 'center', justifyContent: 'center'}} onClick={(e) => e.target.classList.contains('player-container') && setHelpOpen(false)}>
          <div className="player-container" style={{maxWidth: '600px', maxHeight: '80vh', background: 'var(--bg-secondary)', borderRadius: '16px', padding: '2rem', border: '1px solid var(--border-color)', boxShadow: 'var(--shadow-heavy)'}}>
            <button className="player-close" onClick={() => setHelpOpen(false)} style={{position: 'absolute', top: '1rem', right: '1rem'}}><i className="fas fa-times"></i></button>
            <h2 style={{marginBottom: '1.5rem', color: 'var(--accent-primary)'}}><i className="fas fa-keyboard"></i> Keyboard Shortcuts</h2>
            <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', color: 'var(--text-primary)'}}>
              <div style={{fontWeight: 600}}>General</div><div></div>
              <div><kbd>Esc</kbd></div><div>Close Modals</div>
              <div><kbd>?</kbd></div><div>Show this help</div>
              <div style={{fontWeight: 600, marginTop: '1rem'}}>Video Player</div><div></div>
              <div><kbd>Space</kbd></div><div>Play/Pause</div>
              <div><kbd>←</kbd> / <kbd>→</kbd></div><div>Previous/Next Video</div>
              <div><kbd>↑</kbd> / <kbd>↓</kbd></div><div>Volume Up/Down</div>
              <div><kbd>Shift</kbd> + <kbd>↑</kbd> / <kbd>↓</kbd></div><div>Playback Speed Up/Down</div>
              <div><kbd>F</kbd></div><div>Toggle Fullscreen</div>
              <div><kbd>P</kbd></div><div>Toggle Picture-in-Picture</div>
              <div><kbd>M</kbd></div><div>Mute/Unmute</div>
              <div style={{fontWeight: 600, marginTop: '1rem'}}>Image Viewer</div><div></div>
              <div><kbd>←</kbd> / <kbd>→</kbd></div><div>Previous/Next Image</div>
            </div>
          </div>
        </div>
      )}

      <div className={`toast ${showToast ? 'show' : ''}`}>{toastMessage}</div>

      <button className="scroll-to-top" style={{display: showScrollTop ? 'flex' : 'none'}} onClick={scrollToTop}>
        <i className="fas fa-arrow-up"></i>
      </button>
    </>
  );
}